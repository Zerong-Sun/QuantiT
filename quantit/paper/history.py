"""Independent July-start paper histories: prior-session signals, next open fills.

One SQLite file per strategy. Each whole trading day runs in a disposable copy;
only a completed day replaces the durable file. Never opens the active paper DB.
"""
from __future__ import annotations

import argparse
import fcntl
from dataclasses import asdict
from datetime import datetime, time, timezone
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from quantit.data.macro import DEFAULT_MACRO_SYMBOLS
from quantit.features.cn_regime import compute_cn_etf_scores
from quantit.features.regime import compute_theme_scores
from quantit.markets.cn import CNAdapter
from quantit.markets.assets import asset_class
from quantit.markets.hk import HKAdapter, all_hstech_symbols
from quantit.markets.registry import MarketRegistry
from quantit.markets.types import Quote
from quantit.markets.us import USAdapter
from quantit.paper.books import DESK_BOOK_IDS, get_book, venue_of
from quantit.paper.broker import PaperBroker
from quantit.paper.db import create_session
from quantit.paper.history_data import adjusted, atomic_json, cn_symbol, digest, load_bundle, nominal_prices, quality_issues
from quantit.paper.models import Order, RecoveryDay
from quantit.paper.recovery import BOOK_SYMBOLS, REFERENCES, copy_database, session_close
from quantit.paper.runner import PaperRunner
from quantit.research.params import active_params_path
from quantit.research.universes import US_QUALITY

VERSION = 1
NAMES = {"us": "美股质量", "us_book": "美股 MA/RSI（股票）", "hk": "港股质量",
         "hk_theme": "港股科技主题（股票/ETF）", "cn": "A 股质量", "cn_etf": "行业 ETF"}
LIMITATIONS = [
    "真实历史日线的模拟成交，不是实际券商成交；固定当前股票池和规则，不是历史时点成分重建",
    "前一完整交易日信号，下一交易日开盘加滑点；没有逐笔订单簿或排队成交数据",
    "期权和认购证附加部分缺少历史链/可靠报价，未加入本历史实验",
    "分红记为应收并计入净值，不提前增加可用现金；未模拟个人税务与实际到账日期",
    "Yahoo 拆股价格恢复和公司行动仍需券商流水交叉核验；缺价估值会明确标记",
    "新策略只在隔离历史账户中模拟；不改变原运行账户或策略晋级状态",
    "港股每手股数采用所存 HKEX 名单快照，未重建期间变更；费用采用明确的简化费率而非券商账单",
    "部分源日线开收盘价超出供应商日内高低范围，保留实际开收盘报价并在数据检查中标注；不据此编造修正价格",
]


def at_open(day, venue):
    zone, hour, minute = {"us": ("America/New_York", 9, 30), "hk": ("Asia/Hong_Kong", 9, 30),
                          "cn": ("Asia/Shanghai", 9, 30)}[venue]
    return datetime.combine(pd.Timestamp(day).date(), time(hour, minute), ZoneInfo(zone)).astimezone(timezone.utc).replace(tzinfo=None)


class NextOpenAdapter:
    def __init__(self, base, raw, signals, day):
        self.base, self.raw, self.signals, self.day = base, raw, signals, pd.Timestamp(day)

    def __getattr__(self, name):
        return getattr(self.base, name)

    def fetch_bars(self, symbol, interval, start, end):
        symbol = self.normalize_symbol(symbol)
        if interval != "1d" or symbol not in self.signals:
            raise ValueError(f"Missing signal bars: {symbol}")
        frame = self.signals[symbol]
        result = frame.loc[(frame.index >= pd.Timestamp(start).normalize()) & (frame.index < self.day)
                           & (frame.index <= pd.Timestamp(end).normalize())].copy()
        # Express adjusted signals in the prior session's actual price units.
        # Subsequent dividends/splits must not change historical absolute thresholds.
        if not result.empty:
            anchor = result.index[-1]
            ratio = self.raw[symbol].loc[anchor, "close"] / result.close.iloc[-1]
            result.loc[:, ["open", "high", "low", "close"]] *= ratio
        return result

    def fetch_quote(self, symbol):
        symbol = self.normalize_symbol(symbol)
        frame = self.raw.get(symbol)
        if frame is None or self.day not in frame.index:
            raise ValueError(f"No opening quote: {symbol} {self.day.date()}")
        row = frame.loc[self.day]
        price = float(row["open"])
        if not math.isfinite(price) or price <= 0 or not float(row["volume"]) > 0:
            raise ValueError(f"Non-tradable opening quote: {symbol}")
        previous = frame.loc[frame.index < self.day]
        prev = float(previous.close.iloc[-1]) if not previous.empty else price
        # Reference is ex-action adjusted before testing daily price limits.
        split = float(row.get("stock_splits", 0)) or 1.0
        prev = prev / split - float(row.get("dividends", 0))
        return Quote(symbol=symbol, market_id=self.market_id, last=price, open=price,
                     high=price, low=price, prev_close=prev, volume=float(row.volume),
                     timestamp=at_open(self.day, self.market_id), delayed=True)

    def lot_size(self, symbol):
        if self.market_id == "hk":
            lots = json.loads(Path(__file__).with_name("history_hk_lots.json").read_text())["lots"]
            canonical = self.normalize_symbol(symbol)
            if canonical not in lots:
                raise ValueError(f"Unknown HK board lot: {canonical}")
            return lots[canonical]
        if self.market_id == "cn" and self.normalize_symbol(symbol).startswith("688"):
            return 200  # conservative STAR lot proxy (no sub-200 initial buys)
        return self.base.lot_size(symbol)

    def validate_quantity(self, symbol, quantity):
        # Side-aware lot validation is in HistoryBroker, including odd-lot exits.
        return [] if isinstance(quantity, int) and quantity > 0 else ["quantity must be a positive integer"]

    def held_mark(self, symbol):
        """Known price for locked holdings; never made available as a fill quote."""
        frame = self.raw.get(symbol)
        prior = frame.loc[frame.index < self.day].dropna(subset=["close"]) if frame is not None else None
        if prior is None or prior.empty or not float(prior.close.iloc[-1]) > 0:
            raise ValueError(f"No prior valuation for held {symbol}")
        return float(prior.close.iloc[-1])


class HistoryBroker(PaperBroker):
    def rejected(self, book, symbol, side, quantity, reason, rationale=None):
        order = Order(account_id=self.get_account(book).id, market_id=book, symbol=symbol,
                      side=side, quantity=quantity, status="rejected", reject_reason=reason,
                      rationale=rationale, created_at=self.now(), commission=0, fill_price=0)
        self.session.add(order)
        self.session.commit()
        return order

    def place_order(self, market_id, symbol, side, quantity, rationale=None):
        adapter = self.adapter_for(market_id)
        canonical = adapter.normalize_symbol(symbol)
        lot = adapter.lot_size(canonical)
        held = self.get_position(market_id, canonical)
        if quantity % lot and not (side == "sell" and held and quantity == held.quantity):
            return self.rejected(market_id, canonical, side, quantity, "Non-board-lot order", rationale)
        try:
            quote = adapter.fetch_quote(canonical)
        except ValueError as exc:
            return self.rejected(market_id, canonical, side, quantity, str(exc), rationale)
        if adapter.market_id == "cn":
            # Conservative daily-open proxy: both directions blocked at limits.
            threshold = .195 if canonical.startswith(("300", "301", "688")) else .095
            if quote.prev_close and abs(quote.last / quote.prev_close - 1) >= threshold:
                return self.rejected(market_id, canonical, side, quantity, "Daily price limit proxy", rationale)
        frame = adapter.raw[canonical]
        prior = frame.loc[frame.index < adapter.day]
        # Limit participation using volume already observed before the fill.
        capacity = int(float(prior.volume.iloc[-1]) * .01) if not prior.empty else 0
        capacity -= sum(o.quantity for o in self.list_orders(market_id)
                        if o.symbol == canonical and o.status == "filled"
                        and o.created_at.date() == self.now().date())
        if quantity > capacity:
            rationale = f"{rationale or ''}; requested {quantity}, prior-volume cap {max(0, capacity)}"
            quantity = capacity // lot * lot
        if quantity <= 0:
            return self.rejected(market_id, canonical, side, 0, "Prior-volume participation exhausted", rationale)
        minimum = {"us": 0.0, "hk": 18.0, "cn": 5.0}[adapter.market_id]
        hk_etf = adapter.market_id == "hk" and asset_class("hk", canonical) == "etf"
        if side == "buy":
            notional = quote.last * (1 + adapter.profile.slippage_rate) * quantity
            rate = adapter.profile.all_in_commission_rate if adapter.market_id == "hk" and not hk_etf else adapter.profile.commission_rate
            fee = notional * rate + max(0, minimum - notional * adapter.profile.commission_rate)
            if notional + fee > self.get_account(market_id).cash:
                return self.rejected(market_id, canonical, side, quantity, "Insufficient cash including minimum fee", rationale)
        order = super().place_order(market_id, canonical, side, int(quantity),
                                    rationale=f"[July history: prior close -> next open] {rationale or ''}")
        if order.status == "filled":
            # Explicit fee assumptions, not a claim about a specific broker tariff.
            commission_base = order.fill_price * order.quantity * adapter.profile.commission_rate
            extra = max(0.0, minimum - commission_base)
            if hk_etf:
                extra -= order.fill_price * order.quantity * adapter.profile.stamp_duty_rate
            account = self.get_account(market_id)
            if extra > account.cash + 1e-8:
                raise ValueError("Minimum fee would overdraw cash")
            account.cash -= extra
            order.commission += extra
            for trade in order.trades:
                trade.commission += extra
            self.session.commit()
        return order


class HistoryRunner(PaperRunner):
    def _bars_map(self, adapter, symbols, start, end):
        # All frames are already in memory; no network thread pool is necessary.
        result = {}
        for symbol in symbols:
            try:
                frame = adapter.fetch_bars(symbol, "1d", start, end)
                if not frame.empty:
                    result[symbol] = frame
            except (ValueError, KeyError):
                continue
        return result

    def _quotes_map(self, adapter, symbols):
        result = {}
        for symbol in symbols:
            try:
                result[symbol] = adapter.fetch_quote(symbol).last
            except (ValueError, KeyError):
                continue
        return result

    def _book_prices(self, adapter, symbols, book):
        held = {p.symbol for p in self.broker.list_positions(book)}
        prices = self._quotes_map(adapter, sorted(set(symbols) | held))
        for symbol in held - set(prices):
            prices[symbol] = adapter.held_mark(symbol)
        return prices


def actions_before_open(broker, book, raw, day) -> tuple[float, list[dict]]:
    receivable, events = 0.0, []
    for position in broker.list_positions(book):
        frame = raw.get(position.symbol)
        if frame is None or day not in frame.index:
            continue
        row = frame.loc[day]
        split = float(row.get("stock_splits", 0))
        if split and split != 1:
            fraction = 0.0
            for lot in position.lots:
                if lot.remaining <= 0:
                    continue
                expanded = lot.remaining * split
                count = int(math.floor(expanded + 1e-7))
                fraction += expanded - count
                lot.quantity = int(round(lot.quantity * split))
                lot.remaining = count
                lot.price /= split
            position.quantity = sum(l.remaining for l in position.lots)
            position.avg_cost /= split
            receivable += fraction * float(row.open)
            events.append({"symbol": position.symbol, "type": "split", "ratio": split})
        dividend = float(row.get("dividends", 0))
        if dividend > 0:
            amount = position.quantity * dividend
            receivable += amount
            events.append({"symbol": position.symbol, "type": "dividend_receivable", "amount": amount})
    broker.session.commit()
    return receivable, events


def marked_positions(broker, book, raw, day):
    rows, stale = [], []
    for position in broker.list_positions(book):
        frame = raw.get(position.symbol)
        available = frame.loc[frame.index <= day].dropna(subset=["close"]) if frame is not None else None
        if available is None or available.empty:
            raise ValueError(f"Cannot mark {position.symbol}")
        price = float(available.close.iloc[-1])
        asof = available.index[-1]
        if asof != day or not float(available.volume.iloc[-1]) > 0:
            stale.append(position.symbol)
        rows.append({"symbol": position.symbol, "quantity": position.quantity,
                     "avg_cost": position.avg_cost, "close": price, "value": price * position.quantity,
                     "price_date": str(asof.date())})
    return rows, stale


def model_rebalance(broker, book, scores, config, step, raw, day):
    if step % config["rebalance"]:
        return
    if day not in scores.index or scores.loc[day].dropna().empty:
        raise ValueError(f"Missing as-of model signal for {day.date()}")
    adapter = broker.adapter_for(book)
    ranked = scores.loc[day].dropna().sort_values(ascending=False)
    prices = {}
    for instrument in ranked.index:
        symbol = cn_symbol(instrument)
        try:
            prices[symbol] = adapter.fetch_quote(symbol).last
        except ValueError:
            continue
        if len(prices) >= config["top_k"]:
            break
    selected = list(prices)
    positions = {p.symbol: p for p in broker.list_positions(book)}
    locked = set()
    for symbol in positions:
        try:
            prices[symbol] = adapter.fetch_quote(symbol).last
        except ValueError:
            prices[symbol] = adapter.held_mark(symbol)
            locked.add(symbol)
    account = broker.get_account(book)
    equity = account.cash + sum(p.quantity * prices[s] for s, p in positions.items())
    desired = {s: equity * .98 / config["top_k"] for s in selected}
    current = {s: p.quantity * prices[s] for s, p in positions.items()}
    delta = {s: desired.get(s, 0) - current.get(s, 0) for s in prices}
    for symbol in locked:
        delta[symbol] = 0.0
    turnover = sum(abs(x) for x in delta.values())
    scale = min(1.0, config["turnover_limit"] * equity / turnover) if turnover else 0.0
    for side in ("sell", "buy"):
        for symbol, amount in sorted(delta.items(), key=lambda x: x[1]):
            if (side == "sell" and amount >= 0) or (side == "buy" and amount <= 0):
                continue
            lot = adapter.lot_size(symbol)
            quantity = int(abs(amount) * scale / prices[symbol] / lot) * lot
            if side == "sell" and symbol not in desired and scale == 1:
                quantity = positions[symbol].quantity
            if side == "buy":
                affordable = max(0, (broker.get_account(book).cash - 5) / (prices[symbol] * 1.001))
                quantity = min(quantity, int(affordable / lot) * lot)
            if quantity > 0:
                broker.place_order(book, symbol, side, quantity, rationale="Frozen pre-July model/rule ranking")


def read_days(path: Path) -> list[dict]:
    if not path.exists():
        return []
    session = create_session(f"sqlite:///{path}")
    try:
        return [json.loads(row.detail) for row in session.query(RecoveryDay).order_by(RecoveryDay.day)]
    finally:
        engine = session.get_bind()
        session.close()
        engine.dispose()


def run_book(root, strategy, book, raw, signal_frames, calendar, config, scores, hk_scores, cn_scores, start, end, feed_id):
    path = root / "books" / f"{strategy}.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    previous = read_days(path)
    done = {row["day"] for row in previous}
    initial = get_book(book).cash
    errors = []
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    venue = venue_of(book)
    days = [d for d in calendar if pd.Timestamp(start) <= d <= pd.Timestamp(end) and session_close(d, venue) <= now]
    for step, day in enumerate(days):
        day_text = str(day.date())
        if day_text in done:
            continue
        working = path.with_suffix(".pending.db")
        working.unlink(missing_ok=True)  # disposable, never the durable account
        if path.exists():
            copy_database(path, working)
        session = create_session(f"sqlite:///{working}")
        registry = MarketRegistry()
        base = {"us": USAdapter, "hk": HKAdapter, "cn": CNAdapter}[venue]()
        registry.register(NextOpenAdapter(base, raw, signal_frames, day))
        broker = HistoryBroker(session, registry, now=lambda d=day: at_open(d, venue), max_quote_age_days=0)
        try:
            if not previous:
                broker.ensure_accounts()
            receivable = previous[-1]["receivable"] if previous else 0.0
            entitlement, corporate = actions_before_open(broker, book, raw, day)
            receivable += entitlement
            before_ids = {o.id for o in broker.list_orders(book)}
            if scores is not None:
                model_rebalance(broker, book, scores, config, step, raw, day)
            else:
                runner = HistoryRunner(broker, us_watch=US_QUALITY, hk_warrants=(),
                                       hk_scores=hk_scores.loc[hk_scores.index < day] if not hk_scores.empty else hk_scores,
                                       cn_scores=cn_scores.loc[cn_scores.index < day] if not cn_scores.empty else cn_scores,
                                       recovery_mode=True)
                runner.tick(markets=(book,))
                if runner.last_error:
                    raise ValueError(runner.last_error)
            positions, stale = marked_positions(broker, book, raw, day)
            account = broker.get_account(book)
            orders = [{"symbol": o.symbol, "side": o.side, "quantity": o.quantity, "price": o.fill_price,
                       "fee": o.commission, "status": o.status, "reason": o.reject_reason or o.rationale}
                      for o in broker.list_orders(book) if o.id not in before_ids]
            equity = account.cash + receivable + sum(p["value"] for p in positions)
            prior_equity = previous[-1]["equity"] if previous else initial
            peak = max([initial, equity] + [r["equity"] for r in previous])
            row = {"day": day_text, "signal_through": str(signal_frames[REFERENCES[venue]].index[
                    signal_frames[REFERENCES[venue]].index < day].max().date()),
                   "cash": account.cash, "receivable": receivable, "equity": equity,
                   "daily_pnl": equity - prior_equity, "total_return": equity / initial - 1,
                   "drawdown": equity / peak - 1, "fees": sum(o["fee"] for o in orders),
                   "fills": sum(o["status"] == "filled" for o in orders),
                   "rejected": sum(o["status"] != "filled" for o in orders),
                   "positions": positions, "orders": orders, "corporate_actions": corporate,
                   "stale_symbols": stale, "status": "estimated" if stale else "complete", "feed": feed_id}
            session.add(RecoveryDay(market_id=book, day=day_text, status=row["status"],
                                    detail=json.dumps(row, ensure_ascii=False), equity=equity))
            session.commit()
        except Exception as exc:
            errors.append({"strategy": strategy, "day": day_text, "error": str(exc)})
            # Fail closed; retry from the previous committed day on the next pass.
            break
        finally:
            engine = session.get_bind()
            session.close()
            engine.dispose()
        working.replace(path)  # atomic day commit; after a crash pending files are disposable
        previous.append(row)
        done.add(day_text)
    return previous, errors


def run(root: Path, feed: Path, signals: Path, start: str, end: str) -> dict:
    """Serialize whole-history updates; each book/day remains independently durable."""
    root.mkdir(parents=True, exist_ok=True)
    import os
    from quantit.research.params import clear_params_cache
    before = os.environ.get("QUANTIT_ACTIVE_PARAMS")
    with (root / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            return _run(root, feed, signals, start, end)
        finally:
            if before is None:
                os.environ.pop("QUANTIT_ACTIVE_PARAMS", None)
            else:
                os.environ["QUANTIT_ACTIVE_PARAMS"] = before
            clear_params_cache()


def _run(root: Path, feed: Path, signals: Path, start: str, end: str) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    feed_manifest, frames = load_bundle(feed)
    raw = {s: nominal_prices(f) for s, f in frames.items()}
    signal_frames = {s: adjusted(f) for s, f in frames.items()}
    signal_manifest = json.loads((signals / "manifest.json").read_text())
    if signal_manifest["start"] != start:
        raise ValueError("Prediction start differs from history start")
    for name in signal_manifest["strategies"]:
        if digest(signals / f"{name}.parquet") != signal_manifest.get("files", {}).get(name):
            raise ValueError(f"Changed or unverified model predictions: {name}")
    params = active_params_path()
    frozen = root / "parameters.yaml"
    if not frozen.exists():
        frozen.write_text(params.read_text() if params.is_file() else "{}\n")
    import os
    from quantit.research.params import clear_params_cache
    os.environ["QUANTIT_ACTIVE_PARAMS"] = str(frozen)
    clear_params_cache()
    contract = {"version": VERSION, "start": start, "signal_strategies": signal_manifest["strategies"],
                "parameters_sha256": digest(frozen),
                "rule_source": {str(p): digest(p) for p in sorted((Path(__file__).parents[1] / "strategy").glob("*.py"))},
                "engine_sha256": digest(Path(__file__)),
                "execution_sources": {p.name: digest(p) for p in [
                    Path(__file__).with_name("broker.py"), Path(__file__).with_name("runner.py"),
                    Path(__file__).with_name("history_data.py"), Path(__file__).with_name("history_hk_lots.json"),
                    Path(__file__).with_name("history_actions.json")]},
                "initial_cash": {"us": 100000, "hk": 1000000, "cn": 1000000},
                "fill": "previous closed session signals / next open; 1% prior-volume participation",
                "minimum_commission": {"us": 0, "hk": 18, "cn": 5},
                "profiles": {cls.market_id: asdict(cls().profile) for cls in (USAdapter, HKAdapter, CNAdapter)},
                "limitations": LIMITATIONS}
    protocol = root / "protocol.json"
    if protocol.exists() and json.loads(protocol.read_text()) != contract:
        raise ValueError("Frozen history contract changed; create a separate history instead")
    atomic_json(protocol, contract)
    macro_parts = [signal_frames[s]["close"].rename(name) for name, s in DEFAULT_MACRO_SYMBOLS.items() if s in frames]
    macros = pd.concat(macro_parts, axis=1).sort_index() if macro_parts else pd.DataFrame()
    # US close becomes available on the following Asian calendar day.
    macros.index = macros.index + pd.Timedelta(days=1)
    macros = macros.ffill()
    hk_scores = compute_theme_scores({s: signal_frames[s] for s in all_hstech_symbols() if s in frames}, macros)
    cn_scores = compute_cn_etf_scores({s: signal_frames[s] for s in BOOK_SYMBOLS["cn_etf"] if s in frames}, macros)
    rows = []
    data_issues = {symbol: quality_issues(frame, feed_manifest["symbols"][symbol]["venue"])
                   for symbol, frame in frames.items()}
    for strategy in (*DESK_BOOK_IDS, *signal_manifest["strategies"]):
        model_config = signal_manifest["strategies"].get(strategy)
        book = "cn" if model_config else strategy
        venue = venue_of(book)
        reference = frames.get(REFERENCES[venue])
        if reference is None:
            rows.append({"id": strategy, "name": NAMES.get(strategy, strategy), "status": "blocked",
                         "error": "Missing market calendar", "days": []})
            continue
        predictions = pd.read_parquet(signals / f"{strategy}.parquet") if model_config else None
        required = ({cn_symbol(s) for s in predictions.columns} if model_config else
                    {s for s in BOOK_SYMBOLS[book] if asset_class(venue, s) in {"equity", "etf"}})
        hard_issues = {s: [x for x in data_issues.get(s, []) if x.get("severity") != "warning"] for s in required}
        invalid = {s: hard_issues.get(s) or "missing feed" for s in sorted(required)
                   if s not in frames or hard_issues.get(s)}
        if invalid:
            ledger = read_days(root / "books" / f"{strategy}.db")
            errors = [{"strategy": strategy, "day": start, "error": f"Data quality gate: {invalid}"}]
        else:
            ledger, errors = run_book(root, strategy, book, raw, signal_frames, reference.index,
                                     model_config["portfolio"] if model_config else {}, predictions,
                                     hk_scores, cn_scores, start, end, str(feed))
        latest = ledger[-1] if ledger else {}
        record = {"id": strategy, "name": model_config["name"] if model_config else NAMES[strategy],
                  "currency": get_book(book).currency, "initial_cash": get_book(book).cash,
                  "status": "blocked" if errors else "ready", "error": errors[0] if errors else None,
                  "last_day": latest.get("day"), "equity": latest.get("equity"),
                  "total_return": latest.get("total_return"),
                  "max_drawdown": min((d["drawdown"] for d in ledger), default=0.0),
                  "fees": sum(d["fees"] for d in ledger), "fills": sum(d["fills"] for d in ledger),
                  "stale_days": sum(bool(d["stale_symbols"]) for d in ledger),
                  "sessions": len(ledger), "model": model_config.get("model") if model_config else None,
                  "days": [{k: v for k, v in d.items() if k not in {"orders", "positions", "corporate_actions"}} for d in ledger]}
        atomic_json(root / f"{strategy}.json", record)
        rows.append(record)
        print(strategy, len(ledger), record["equity"], errors, flush=True)
    report = {"start": start, "requested_end": end, "updated_at": datetime.now(timezone.utc).isoformat(),
              "mode": "isolated daily paper history", "limitations": LIMITATIONS, "strategies": rows,
              "feed": {"downloaded_at": feed_manifest["downloaded_at"],
                       "missing": {s: x["error"] for s, x in feed_manifest["symbols"].items() if "error" in x},
                       "corrections": {s: x["correction"] for s, x in feed_manifest["symbols"].items() if x.get("correction")},
                       "latest_ohlc_corrections": {s: x["latest_check"] for s, x in feed_manifest["symbols"].items()
                                                   if x.get("latest_check", {}) and x["latest_check"].get("differences")},
                       "quality_issues": {s: v for s, v in data_issues.items() if v}}}
    atomic_json(root / "report.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--feed", type=Path, required=True)
    parser.add_argument("--signals", type=Path, required=True)
    parser.add_argument("--start", default="2026-07-01")
    parser.add_argument("--end", required=True)
    args = parser.parse_args()
    run(args.root, args.feed, args.signals, args.start, args.end)


if __name__ == "__main__":
    main()
