"""Periodic paper-trading runner: execute catalog strategies against the book."""

from __future__ import annotations

import threading
import traceback
from collections.abc import Callable
from datetime import date, datetime
from typing import Any

import pandas as pd

from quantit.features.regime import scores_to_theme_weights
from quantit.markets.assets import us_option_root
from quantit.markets.hk import HSTECH_THEMES, all_hstech_symbols
from quantit.markets.cn import CN_ETF_FALLBACK, CN_ETF_THEMES, all_cn_etf_symbols
from quantit.paper.broker import PaperBroker
from quantit.paper.capital import (
    HK_ETF_WATCHLIST,
    HK_WARRANT_SLOT_PCT,
    HK_WARRANT_WATCHLIST,
    PAPER_MAX_DRAWDOWN,
    US_OPTION_SLOT_PCT,
    US_SLOT_PCT,
    US_WATCHLIST,
)
from quantit.research.params import strategy_params, us_primary, hk_primary, cn_primary
from quantit.research.universes import HK_QUALITY, CN_QUALITY
from quantit.strategy.cn_book import CNQualityBookStrategy
from quantit.strategy.hk_book import HKQualityBookStrategy, basket_momentum, invested_fraction
from quantit.strategy.regime import ThemeRotationStrategy, feasible_hk_weights, is_month_end
from quantit.strategy.signals import evaluate_signals, ma_signal, resolve_us_book_action, rsi_signal
from quantit.strategy.tsmom import coerce_vol, tsmom_size


def load_hk_theme_scores() -> pd.DataFrame | None:
    """Best-effort daily HK theme scores. Returns None if macros/bars are missing."""
    from quantit.data.loader import DataLoader
    from quantit.data.macro import MacroLoader
    from quantit.features.regime import compute_theme_scores

    end = pd.Timestamp.utcnow().strftime("%Y-%m-%d")
    start = (pd.Timestamp.utcnow() - pd.Timedelta(days=420)).strftime("%Y-%m-%d")
    loader = DataLoader()
    ohlcv = loader.load_multi(all_hstech_symbols(), start, end, skip_missing=True)
    if not ohlcv:
        return None
    calendar = None
    for df in ohlcv.values():
        calendar = df.index if calendar is None else calendar.union(df.index)
    macros = MacroLoader(loader).load(start, end, calendar=calendar, skip_missing=True)
    scores = compute_theme_scores(ohlcv, macros)
    if scores is None or scores.empty:
        return None
    return scores


def load_cn_theme_scores() -> pd.DataFrame | None:
    """Best-effort daily CN industry-ETF scores. Returns None if bars are missing."""
    from quantit.data.cn_csv import CompositeCNProvider
    from quantit.data.loader import DataLoader
    from quantit.data.macro import MacroLoader
    from quantit.features.cn_regime import compute_cn_etf_scores
    from quantit.policy.calendar import PolicyCalendar

    end = pd.Timestamp.utcnow().strftime("%Y-%m-%d")
    start = (pd.Timestamp.utcnow() - pd.Timedelta(days=420)).strftime("%Y-%m-%d")
    symbols = list(dict.fromkeys([*all_cn_etf_symbols(), CN_ETF_FALLBACK]))
    loader = DataLoader(provider=CompositeCNProvider())
    ohlcv = loader.load_multi(symbols, start, end, skip_missing=True)
    if not ohlcv:
        return None
    calendar = None
    for df in ohlcv.values():
        calendar = df.index if calendar is None else calendar.union(df.index)
    macros = MacroLoader().load(start, end, calendar=calendar, skip_missing=True)
    scores = compute_cn_etf_scores(ohlcv, macros, calendar=PolicyCalendar.load_cn())
    if scores is None or scores.empty:
        return None
    return scores


class PaperRunner:
    """Evaluate US MA/RSI daily, HK theme rotation, and CN industry ETFs on month-end."""

    def __init__(
        self,
        broker: PaperBroker,
        us_watch: tuple[str, ...] = US_WATCHLIST,
        hk_etfs: tuple[str, ...] = HK_ETF_WATCHLIST,
        hk_warrants: tuple[str, ...] = HK_WARRANT_WATCHLIST,
        hk_scores: pd.DataFrame | None = None,
        hk_score_loader: Callable[[], pd.DataFrame | None] | None = None,
        cn_scores: pd.DataFrame | None = None,
        cn_score_loader: Callable[[], pd.DataFrame | None] | None = None,
        us_option_picker: Callable[[str, float, date], str | None] | None = None,
        interval_sec: int = 60,
        eval_interval_sec: float = 0.0,
    ) -> None:
        self.broker = broker
        self.us_watch = us_watch
        self.hk_etfs = hk_etfs
        self.hk_warrants = hk_warrants
        self.hk_scores = hk_scores
        self.hk_score_loader = hk_score_loader
        self.cn_scores = cn_scores
        self.cn_score_loader = cn_score_loader
        self.us_option_picker = us_option_picker
        self.interval_sec = interval_sec
        # Minimum seconds between per-symbol live evaluations (0 disables the
        # throttle). Daily signals only change when a session closes, so polling
        # quote APIs every tick burns free data sources (Yahoo 429, Eastmoney IP
        # bans) for no benefit.
        self.eval_interval_sec = eval_interval_sec
        self.running = False
        self.last_tick: datetime | None = None
        self.last_error: str | None = None
        self.actions: list[dict[str, Any]] = []
        self._acted: set[tuple[str, str, date]] = set()
        self._last_eval: dict[tuple[str, str], datetime] = {}
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def _due(self, market: str, symbol: str, now: datetime, force: bool) -> bool:
        """Throttle live re-evaluations of ``symbol`` unless forced or not configured."""
        if force or self.eval_interval_sec <= 0:
            return True
        last = self._last_eval.get((market, symbol))
        if last is None:
            return True
        return (now - last).total_seconds() >= self.eval_interval_sec

    def _note_eval(self, market: str, symbol: str, now: datetime) -> None:
        self._last_eval[(market, symbol)] = now

    def snapshot(self) -> dict[str, Any]:
        from quantit.markets.assets import allowed_list
        from quantit.paper.capital import PAPER_CASH

        cash = {a.market_id: a.cash for a in self.broker.list_accounts()}
        return {
            "running": self.running,
            "interval_sec": self.interval_sec,
            "last_tick": self.last_tick.isoformat() if self.last_tick else None,
            "last_error": self.last_error,
            "seed_cash": PAPER_CASH,
            "cash": cash,
            "allowed": {mid: allowed_list(mid) for mid in ("us", "hk", "cn")},
            "watchlists": {
                "us": list(self.us_watch),
                "hk": self._hk_equity_watch(),
                "hk_warrants": list(self.hk_warrants),
                "cn": self._cn_equity_watch(),
            },
            "actions": list(reversed(self.actions[-40:])),
        }

    def start_background(self) -> None:
        if self.running:
            return
        self.running = True
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="quantit-paper-runner", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self.running = False
        self._stop.set()

    def _loop(self) -> None:
        self.tick()
        while not self._stop.wait(self.interval_sec):
            if not self.running:
                return
            self.tick()

    def tick(
        self,
        *,
        markets: tuple[str, ...] | None = None,
        force: bool = False,
    ) -> list[dict[str, Any]]:
        """One evaluation pass. Safe to call from tests without the background thread.

        ``markets`` limits which books run (default: US, HK, and CN). ``force`` skips the
        HK/CN month-end gate and today's already-acted marks so a desk can pull the
        rotation and warrant sleeves off-calendar.
        """
        wanted = set(markets) if markets else {"us", "hk", "cn"}
        produced: list[dict[str, Any]] = []
        try:
            if "us" in wanted:
                produced.extend(self._tick_us(force=force))
            if "hk" in wanted:
                produced.extend(self._tick_hk(force=force))
                produced.extend(self._tick_hk_warrants(force=force))
            if "cn" in wanted:
                produced.extend(self._tick_cn(force=force))
            self.last_error = None
        except Exception as exc:
            self.last_error = f"{exc}\n{traceback.format_exc(limit=4)}"
        self.last_tick = self.broker.now()
        return produced

    def _today(self) -> date:
        return self.broker.now().date()

    def _already(self, market: str, symbol: str) -> bool:
        return (market, symbol, self._today()) in self._acted

    def _mark(self, market: str, symbol: str) -> None:
        self._acted.add((market, symbol, self._today()))

    def _record(self, order, extra: str = "") -> dict[str, Any]:
        row = {
            "time": (order.fill_time or order.created_at).isoformat() if order.created_at else None,
            "market_id": order.market_id,
            "symbol": order.symbol,
            "side": order.side,
            "quantity": order.quantity,
            "status": order.status,
            "rationale": extra or order.rationale,
            "reject_reason": order.reject_reason,
        }
        self.actions.append(row)
        if len(self.actions) > 200:
            self.actions = self.actions[-200:]
        return row

    def _tick_us(self, force: bool = False) -> list[dict[str, Any]]:
        adapter = self.broker.registry.get("us")
        end = pd.Timestamp(self.broker.now())
        start = end - pd.Timedelta(days=400)
        out: list[dict[str, Any]] = []
        for symbol in self.us_watch:
            if self._already("us", symbol):
                continue
            now = self.broker.now()
            if not self._due("us", symbol, now, force):
                continue
            self._note_eval("us", symbol, now)
            try:
                bars = adapter.fetch_bars(symbol, "1d", start, end)
            except (ValueError, KeyError):
                continue
            bundle = evaluate_signals("us", symbol, bars)
            primary = us_primary()
            if primary == "tsmom":
                book = next((s for s in bundle["signals"] if s.get("strategy_id") == "tsmom"), None)
            else:
                book = next((s for s in bundle["signals"] if s.get("strategy_id") == "us_book"), None)
            if book is None:
                continue
            if book["action"] not in {"buy", "sell"}:
                continue
            held = self.broker.get_position("us", symbol)
            qty_held = held.quantity if held is not None else 0
            why = book["reason"]
            if book["action"] == "sell":
                if qty_held > 0:
                    if primary == "tsmom":
                        last = float(bars["close"].iloc[-1])
                        values = book.get("values") or {}
                        scale = float(values.get("risk_off_scale") if values.get("risk_off_scale") is not None else 0.3)
                        if last > 0 and scale > 0:
                            vol = coerce_vol(values.get("realized_vol"), 0.15)
                            target_vol = coerce_vol(values.get("target_vol"), 0.15)
                            account = self.broker.get_account("us")
                            equity = account.cash + last * qty_held
                            full = tsmom_size(
                                equity=equity,
                                price=last,
                                realized_vol=vol,
                                target_vol=target_vol,
                                vol_floor=0.05,
                                max_position_pct=US_SLOT_PCT,
                            )
                            target = int(scale * full)
                            cut = qty_held - target
                            if cut > 0:
                                order = self.broker.place_order("us", symbol, "sell", cut, rationale=why)
                                out.append(self._record(order, why))
                        else:
                            order = self.broker.place_order("us", symbol, "sell", qty_held, rationale=why)
                            out.append(self._record(order, why))
                    else:
                        order = self.broker.place_order("us", symbol, "sell", qty_held, rationale=why)
                        out.append(self._record(order, why))
                out.extend(self._close_us_options(symbol, why))
                self._mark("us", symbol)
                continue
            if book["action"] == "buy":
                if self._us_drawdown_breached():
                    continue
                if qty_held == 0:
                    last = float(bars["close"].iloc[-1])
                    if last <= 0:
                        continue
                    account = self.broker.get_account("us")
                    if primary == "tsmom":
                        values = book.get("values") or {}
                        vol = coerce_vol(values.get("realized_vol"), 0.15)
                        target_vol = coerce_vol(values.get("target_vol"), 0.15)
                        equity = account.cash + last * qty_held
                        qty = tsmom_size(
                            equity=equity,
                            price=last,
                            realized_vol=vol,
                            target_vol=target_vol,
                            vol_floor=0.05,
                            max_position_pct=US_SLOT_PCT,
                        )
                    else:
                        budget = min(account.cash * 0.95, account.initial_cash * US_SLOT_PCT)
                        qty = int(budget / last)
                    if qty > 0:
                        order = self.broker.place_order("us", symbol, "buy", qty, rationale=why)
                        out.append(self._record(order, why))
                out.extend(self._open_us_call(symbol, float(bars["close"].iloc[-1]), why))
                self._mark("us", symbol)
        return out

    def _us_options_on(self, underlying: str) -> list:
        root = underlying.strip().upper()
        return [
            p
            for p in self.broker.list_positions("us")
            if us_option_root(p.symbol) == root
        ]

    def _close_us_options(self, underlying: str, why: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for pos in self._us_options_on(underlying):
            if pos.quantity <= 0:
                continue
            order = self.broker.place_order(
                "us", pos.symbol, "sell", pos.quantity, rationale=f"Close overlay: {why}"
            )
            out.append(self._record(order, why))
        return out

    def _open_us_call(self, underlying: str, spot: float, why: str) -> list[dict[str, Any]]:
        if self.us_option_picker is None or spot <= 0:
            return []
        if self._us_options_on(underlying):
            return []
        try:
            occ = self.us_option_picker(underlying, spot, self._today())
        except Exception:
            return []
        if not occ:
            return []
        try:
            quote = self.broker.registry.get("us").fetch_quote(occ)
            last = float(quote.last)
        except (ValueError, KeyError):
            return []
        if last <= 0:
            return []
        account = self.broker.get_account("us")
        budget = min(account.cash * 0.90, account.initial_cash * US_OPTION_SLOT_PCT)
        qty = int(budget / (last * 100))
        if qty <= 0:
            qty = 1
        cost = last * 1.001 * 100 * qty
        if cost > account.cash:
            return []
        order = self.broker.place_order(
            "us", occ, "buy", qty, rationale=f"ATM call overlay on {underlying}: {why}"
        )
        return [self._record(order, why)]

    def _us_drawdown_breached(self) -> bool:
        account = self.broker.get_account("us")
        if account.initial_cash <= 0:
            return False
        adapter = self.broker.registry.get("us")
        equity = account.cash
        for pos in self.broker.list_positions("us"):
            try:
                last = adapter.fetch_quote(pos.symbol).last
            except (ValueError, KeyError):
                last = pos.avg_cost
            equity += last * pos.quantity
        return equity < account.initial_cash * (1.0 - PAPER_MAX_DRAWDOWN)

    def _tick_hk_warrants(self, force: bool = False) -> list[dict[str, Any]]:
        adapter = self.broker.registry.get("hk")
        end = pd.Timestamp(self.broker.now())
        start = end - pd.Timedelta(days=400)
        out: list[dict[str, Any]] = []
        for symbol in self.hk_warrants:
            if not force and self._already("hk", symbol):
                continue
            now = self.broker.now()
            if not self._due("hk", symbol, now, force):
                continue
            self._note_eval("hk", symbol, now)
            try:
                bars = adapter.fetch_bars(symbol, "1d", start, end)
            except (ValueError, KeyError):
                continue
            book = resolve_us_book_action(ma_signal(bars), rsi_signal(bars))
            if book["action"] not in {"buy", "sell"}:
                continue
            held = self.broker.get_position("hk", symbol)
            qty_held = held.quantity if held is not None else 0
            why = f"HK warrant/CBBC: {book['reason']}"
            if book["action"] == "sell" and qty_held > 0:
                order = self.broker.place_order("hk", symbol, "sell", qty_held, rationale=why)
                self._mark("hk", symbol)
                out.append(self._record(order, why))
                continue
            if book["action"] == "buy" and qty_held == 0:
                last = float(bars["close"].iloc[-1])
                if last <= 0:
                    continue
                account = self.broker.get_account("hk")
                budget = min(account.cash * 0.90, account.initial_cash * HK_WARRANT_SLOT_PCT)
                qty = int(budget / last)
                lot = adapter.lot_size(symbol)
                if lot > 1:
                    qty = (qty // lot) * lot
                if qty <= 0:
                    continue
                order = self.broker.place_order("hk", symbol, "buy", qty, rationale=why)
                self._mark("hk", symbol)
                out.append(self._record(order, why))
        return out

    def _hk_equity_watch(self) -> list[str]:
        if hk_primary() == "hk_quality_book":
            return list(HK_QUALITY) + list(self.hk_etfs)
        return list(all_hstech_symbols()) + list(self.hk_etfs)

    def _cn_equity_watch(self) -> list[str]:
        if cn_primary() == "cn_quality_book":
            return list(CN_QUALITY)
        return list(all_cn_etf_symbols()) + [CN_ETF_FALLBACK]

    def _tick_hk(self, force: bool = False) -> list[dict[str, Any]]:
        if hk_primary() == "hk_quality_book":
            return self._tick_hk_quality(force=force)
        if not force and self._already("hk", "HSTECH-ROTATION"):
            return []

        adapter = self.broker.registry.get("hk")
        end = pd.Timestamp(self.broker.now())
        start = end - pd.Timedelta(days=400)
        try:
            calendar_bars = adapter.fetch_bars("0700.HK", "1d", start, end)
        except (ValueError, KeyError):
            return []
        calendar = pd.DatetimeIndex(calendar_bars.index).normalize()
        ts = pd.Timestamp(self.broker.now()).normalize()
        if calendar.empty:
            return []
        # Use last available session on/before now.
        asof = calendar[calendar <= ts]
        if asof.empty:
            return []
        session = asof[-1]
        if not force and not is_month_end(calendar, session):
            return []

        scores = self.hk_scores
        if scores is None and self.hk_score_loader is not None:
            try:
                scores = self.hk_score_loader()
            except Exception as exc:
                self.last_error = f"HK scores: {exc}"
                return []
        if scores is None or scores.empty:
            return []

        row = scores.asof(session)
        if row is None or not isinstance(row, pd.Series) or row.isna().all():
            return []
        theme_scores = {k: float(v) for k, v in row.items() if k in HSTECH_THEMES}
        if not theme_scores:
            return []
        hk_cfg = strategy_params("theme_rotation")
        strat = ThemeRotationStrategy(
            scores=scores,
            cash_threshold=float(hk_cfg.get("cash_threshold", -0.5)),
            risk_off_invested=float(hk_cfg.get("risk_off_invested", 0.40)),
            equal_weight_band=float(hk_cfg.get("equal_weight_band", 0.25)),
            turnover_band=float(hk_cfg.get("turnover_band", 0.02)),
        )
        theme_w = scores_to_theme_weights(
            theme_scores,
            cash_threshold=strat.cash_threshold,
            risk_off_invested=strat.risk_off_invested,
            equal_weight_band=strat.equal_weight_band,
        )
        members = list(all_hstech_symbols()) + list(self.hk_etfs)
        prices: dict[str, float] = {}
        for symbol in members:
            try:
                q = adapter.fetch_quote(symbol)
            except (ValueError, KeyError):
                continue
            if q.last > 0:
                prices[symbol] = q.last
        target = strat._expand_to_symbols(theme_w, prices)
        account = self.broker.get_account("hk")
        equity = account.cash
        for pos in self.broker.list_positions("hk"):
            px = prices.get(pos.symbol)
            if px:
                equity += px * pos.quantity
        lot_sizes = {sym: adapter.lot_size(sym) for sym in set(prices) | set(target)}
        target = feasible_hk_weights(target, prices, equity, lot_sizes)
        orders = self._rebalance_hk(
            target, prices, session, turnover_band=strat.turnover_band, force=force
        )
        self._mark("hk", "HSTECH-ROTATION")
        return orders

    def _tick_hk_quality(self, force: bool = False) -> list[dict[str, Any]]:
        if not force and self._already("hk", "HK-QUALITY-BOOK"):
            return []
        adapter = self.broker.registry.get("hk")
        end = pd.Timestamp(self.broker.now())
        start = end - pd.Timedelta(days=500)
        ohlcv: dict[str, pd.DataFrame] = {}
        calendar = None
        for symbol in HK_QUALITY:
            try:
                bars = adapter.fetch_bars(symbol, "1d", start, end)
            except (ValueError, KeyError):
                continue
            if bars is None or bars.empty:
                continue
            ohlcv[symbol] = bars
            calendar = bars.index if calendar is None else calendar.union(bars.index)
        if not ohlcv or calendar is None:
            return []
        calendar = pd.DatetimeIndex(calendar).normalize().sort_values().unique()
        ts = pd.Timestamp(self.broker.now()).normalize()
        asof = calendar[calendar <= ts]
        if asof.empty:
            return []
        session = asof[-1]
        if not force and not is_month_end(calendar, session):
            return []
        cfg = strategy_params("hk_quality_book")
        defaults = HKQualityBookStrategy()
        lookback = int(cfg.get("lookback", defaults.lookback))
        skip = int(cfg.get("skip", defaults.skip))
        risk_off_scale = float(cfg.get("risk_off_scale", defaults.risk_off_scale))
        invested_on = float(cfg.get("invested_on", defaults.invested_on))
        mom = basket_momentum(ohlcv, lookback, skip)
        mom_val: float | None = None
        if not mom.empty:
            hit = mom.asof(session)
            if hit is not None and not pd.isna(hit):
                mom_val = float(hit)
        frac = invested_fraction(mom_val, invested_on=invested_on, risk_off_scale=risk_off_scale)
        prices: dict[str, float] = {}
        for symbol in HK_QUALITY:
            try:
                q = adapter.fetch_quote(symbol)
            except (ValueError, KeyError):
                continue
            if q.last > 0:
                prices[symbol] = q.last
        quoted = [s for s in HK_QUALITY if s in prices]
        n = len(quoted)
        target = {s: (frac / n) for s in quoted} if n and frac > 0 else {}
        account = self.broker.get_account("hk")
        equity = account.cash
        for pos in self.broker.list_positions("hk"):
            px = prices.get(pos.symbol)
            if px:
                equity += px * pos.quantity
        lot_sizes = {sym: adapter.lot_size(sym) for sym in set(prices) | set(target)}
        target = feasible_hk_weights(target, prices, equity, lot_sizes, fallback="")
        if mom_val is None:
            why = f"HK quality basket TSMOM rebalance {session.date()} (momentum unavailable)"
        else:
            why = (
                f"HK quality basket TSMOM rebalance {session.date()} "
                f"(mom={mom_val:.2%} invested={frac:.0%})"
            )
        orders = self._rebalance_hk(
            target,
            prices,
            session,
            turnover_band=float(cfg.get("turnover_band", defaults.turnover_band)),
            force=force,
            why=why,
        )
        self._mark("hk", "HK-QUALITY-BOOK")
        return orders

    def _tick_cn(self, force: bool = False) -> list[dict[str, Any]]:
        if cn_primary() == "cn_quality_book":
            return self._tick_cn_quality(force=force)
        if not force and self._already("cn", "CN-ETF-ROTATION"):
            return []

        adapter = self.broker.registry.get("cn")
        end = pd.Timestamp(self.broker.now())
        start = end - pd.Timedelta(days=400)
        try:
            calendar_bars = adapter.fetch_bars(CN_ETF_FALLBACK, "1d", start, end)
        except (ValueError, KeyError):
            return []
        calendar = pd.DatetimeIndex(calendar_bars.index).normalize()
        ts = pd.Timestamp(self.broker.now()).normalize()
        if calendar.empty:
            return []
        asof = calendar[calendar <= ts]
        if asof.empty:
            return []
        session = asof[-1]
        if not force and not is_month_end(calendar, session):
            return []

        scores = self.cn_scores
        if scores is None and self.cn_score_loader is not None:
            try:
                scores = self.cn_score_loader()
            except Exception as exc:
                self.last_error = f"CN scores: {exc}"
                return []
        if scores is None or scores.empty:
            return []

        row = scores.asof(session)
        if row is None or not isinstance(row, pd.Series) or row.isna().all():
            return []
        theme_scores = {k: float(v) for k, v in row.items() if k in CN_ETF_THEMES}
        if not theme_scores:
            return []
        cn_cfg = strategy_params("cn_etf_rotation")
        strat = ThemeRotationStrategy(
            scores=scores,
            themes=CN_ETF_THEMES,
            cash_threshold=float(cn_cfg.get("cash_threshold", -0.5)),
            risk_off_invested=float(cn_cfg.get("risk_off_invested", 0.40)),
            equal_weight_band=float(cn_cfg.get("equal_weight_band", 0.25)),
            turnover_band=float(cn_cfg.get("turnover_band", 0.02)),
        )
        theme_w = scores_to_theme_weights(
            theme_scores,
            cash_threshold=strat.cash_threshold,
            risk_off_invested=strat.risk_off_invested,
            equal_weight_band=strat.equal_weight_band,
        )
        members = list(all_cn_etf_symbols()) + [CN_ETF_FALLBACK]
        prices: dict[str, float] = {}
        for symbol in members:
            try:
                q = adapter.fetch_quote(symbol)
            except (ValueError, KeyError):
                continue
            if q.last > 0:
                prices[symbol] = q.last
        target = strat._expand_to_symbols(theme_w, prices)
        account = self.broker.get_account("cn")
        equity = account.cash
        for pos in self.broker.list_positions("cn"):
            px = prices.get(pos.symbol)
            if px:
                equity += px * pos.quantity
        lot_sizes = {sym: adapter.lot_size(sym) for sym in set(prices) | set(target)}
        target = feasible_hk_weights(
            target, prices, equity, lot_sizes, fallback=CN_ETF_FALLBACK
        )
        orders = self._rebalance_hk(
            target,
            prices,
            session,
            turnover_band=strat.turnover_band,
            force=force,
            market_id="cn",
            why=f"CN ETF theme rotation rebalance {session.date()}",
        )
        self._mark("cn", "CN-ETF-ROTATION")
        return orders

    def _tick_cn_quality(self, force: bool = False) -> list[dict[str, Any]]:
        if not force and self._already("cn", "CN-QUALITY-BOOK"):
            return []
        adapter = self.broker.registry.get("cn")
        end = pd.Timestamp(self.broker.now())
        start = end - pd.Timedelta(days=500)
        ohlcv: dict[str, pd.DataFrame] = {}
        calendar = None
        for symbol in CN_QUALITY:
            try:
                bars = adapter.fetch_bars(symbol, "1d", start, end)
            except (ValueError, KeyError):
                continue
            if bars is None or bars.empty:
                continue
            ohlcv[symbol] = bars
            calendar = bars.index if calendar is None else calendar.union(bars.index)
        if not ohlcv or calendar is None:
            return []
        calendar = pd.DatetimeIndex(calendar).normalize().sort_values().unique()
        ts = pd.Timestamp(self.broker.now()).normalize()
        asof = calendar[calendar <= ts]
        if asof.empty:
            return []
        session = asof[-1]
        if not force and not is_month_end(calendar, session):
            return []
        cfg = strategy_params("cn_quality_book")
        defaults = CNQualityBookStrategy()
        lookback = int(cfg.get("lookback", defaults.lookback))
        skip = int(cfg.get("skip", defaults.skip))
        risk_off_scale = float(cfg.get("risk_off_scale", defaults.risk_off_scale))
        invested_on = float(cfg.get("invested_on", defaults.invested_on))
        mom = basket_momentum(ohlcv, lookback, skip)
        mom_val: float | None = None
        if not mom.empty:
            hit = mom.asof(session)
            if hit is not None and not pd.isna(hit):
                mom_val = float(hit)
        frac = invested_fraction(mom_val, invested_on=invested_on, risk_off_scale=risk_off_scale)
        prices: dict[str, float] = {}
        for symbol in CN_QUALITY:
            try:
                q = adapter.fetch_quote(symbol)
            except (ValueError, KeyError):
                continue
            if q.last > 0:
                prices[symbol] = q.last
        quoted = [s for s in CN_QUALITY if s in prices]
        n = len(quoted)
        target = {s: (frac / n) for s in quoted} if n and frac > 0 else {}
        account = self.broker.get_account("cn")
        equity = account.cash
        for pos in self.broker.list_positions("cn"):
            px = prices.get(pos.symbol)
            if px:
                equity += px * pos.quantity
        lot_sizes = {sym: adapter.lot_size(sym) for sym in set(prices) | set(target)}
        target = feasible_hk_weights(target, prices, equity, lot_sizes, fallback="")
        if mom_val is None:
            why = f"CN quality basket TSMOM rebalance {session.date()} (momentum unavailable)"
        else:
            why = (
                f"CN quality basket TSMOM rebalance {session.date()} "
                f"(mom={mom_val:.2%} invested={frac:.0%})"
            )
        orders = self._rebalance_hk(
            target,
            prices,
            session,
            turnover_band=float(cfg.get("turnover_band", defaults.turnover_band)),
            force=force,
            market_id="cn",
            why=why,
        )
        self._mark("cn", "CN-QUALITY-BOOK")
        return orders

    def _rebalance_hk(
        self,
        target_weights: dict[str, float],
        prices: dict[str, float],
        session: pd.Timestamp,
        turnover_band: float = 0.02,
        force: bool = False,
        market_id: str = "hk",
        why: str | None = None,
    ) -> list[dict[str, Any]]:
        account = self.broker.get_account(market_id)
        equity = account.cash
        positions = self.broker.list_positions(market_id)
        held = {p.symbol: p.quantity for p in positions}
        for symbol, qty in held.items():
            px = prices.get(symbol)
            if px:
                equity += px * qty
        if equity <= 0:
            return []

        adapter = self.broker.registry.get(market_id)
        sells: list[tuple[str, int]] = []
        buys: list[tuple[str, int]] = []
        for symbol in set(prices) | set(held):
            px = prices.get(symbol)
            if px is None or px <= 0:
                continue
            target_qty = int(equity * target_weights.get(symbol, 0.0) / px)
            lot = adapter.lot_size(symbol)
            if lot > 1:
                target_qty = (target_qty // lot) * lot
            current = held.get(symbol, 0)
            diff = target_qty - current
            if diff == 0:
                continue
            if current > 0 and target_qty > 0 and abs(diff) / current <= turnover_band:
                continue
            if diff < 0:
                sells.append((symbol, min(-diff, current)))
            else:
                buys.append((symbol, diff))

        estimated_cash = account.cash
        for symbol, qty in sells:
            px = prices.get(symbol, 0.0)
            estimated_cash += qty * px * (1 - 0.002)
        buy_notional = sum(qty * prices[s] for s, qty in buys if s in prices)
        if buy_notional > estimated_cash * 0.98 and buy_notional > 0:
            scale = (estimated_cash * 0.98) / buy_notional
            buys = [(s, int(qty * scale)) for s, qty in buys]
            adapter = self.broker.registry.get(market_id)
            scaled: list[tuple[str, int]] = []
            for symbol, qty in buys:
                lot = adapter.lot_size(symbol)
                if lot > 1:
                    qty = (qty // lot) * lot
                if qty > 0:
                    scaled.append((symbol, qty))
            buys = scaled

        rationale = why or f"HK tech theme rotation rebalance {session.date()}"
        if force:
            rationale += " (manual)"
        out: list[dict[str, Any]] = []
        for symbol, qty in sells:
            if qty <= 0:
                continue
            order = self.broker.place_order(market_id, symbol, "sell", qty, rationale=rationale)
            out.append(self._record(order, rationale))
        for symbol, qty in buys:
            if qty <= 0:
                continue
            order = self.broker.place_order(market_id, symbol, "buy", qty, rationale=rationale)
            out.append(self._record(order, rationale))
        return out
