"""Mark-to-market book, allocation, and period P&L for the paper desk."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from quantit.markets.assets import asset_class, multiplier
from quantit.paper.broker import PaperBroker
from quantit.paper.models import Account, Position, Trade


def _period_starts(now: datetime) -> dict[str, datetime]:
    day = datetime(now.year, now.month, now.day)
    week = day - timedelta(days=day.weekday())
    month = datetime(now.year, now.month, 1)
    return {"day": day, "week": week, "month": month}


def _notional(market_id: str, symbol: str, quantity: int, price: float) -> float:
    return float(quantity) * float(price) * multiplier(market_id, symbol)


def _finite(value: float | None) -> float | None:
    if value is None:
        return None
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def _normalize_frame(df: pd.DataFrame) -> pd.DataFrame:
    dated = df.copy()
    idx = pd.to_datetime(dated.index)
    tz = getattr(idx, "tz", None)
    if tz is not None:
        idx = idx.tz_convert("UTC").tz_localize(None)
    dated.index = idx.normalize()
    return dated.sort_index()


def _load_frame(adapter, symbol: str, now: datetime) -> pd.DataFrame | None:
    end = pd.Timestamp(now).normalize() + pd.Timedelta(days=2)
    start = end - pd.Timedelta(days=45)
    try:
        df = adapter.fetch_bars(symbol, "1d", start, end)
    except Exception:
        return None
    if df is None or df.empty or "close" not in df.columns:
        return None
    return _normalize_frame(df)


def _last_prev(frame: pd.DataFrame | None) -> tuple[float | None, float | None]:
    if frame is None or frame.empty:
        return None, None
    last = _finite(float(frame["close"].iloc[-1]))
    prev = _finite(float(frame["close"].iloc[-2])) if len(frame) > 1 else last
    return last, prev


def _close_before(frame: pd.DataFrame | None, when: datetime) -> float | None:
    """Last session close strictly before ``when``; else first print on/after it."""
    if frame is None or frame.empty:
        return None
    cutoff = pd.Timestamp(when).normalize()
    prior = frame.loc[frame.index < cutoff, "close"]
    if not prior.empty:
        return _finite(float(prior.iloc[-1]))
    later = frame.loc[frame.index >= cutoff, "close"]
    if not later.empty:
        return _finite(float(later.iloc[0]))
    return None


def _qty_map(positions: list[Position], market_id: str) -> dict[str, int]:
    return {p.symbol: int(p.quantity) for p in positions if p.market_id == market_id and p.quantity > 0}


def _replay(
    account: Account,
    qty: dict[str, int],
    trades: list[Trade],
    as_of: datetime,
) -> tuple[float, dict[str, int]]:
    cash = float(account.cash)
    held = dict(qty)
    for trade in trades:
        if trade.market_id != account.market_id or trade.timestamp <= as_of:
            continue
        side = (trade.side or "").lower()
        if side not in {"buy", "sell"}:
            continue
        notion = _notional(trade.market_id, trade.symbol, trade.quantity, trade.price)
        current = held.get(trade.symbol, 0)
        if side == "buy":
            cash += notion + float(trade.commission)
            held[trade.symbol] = current - trade.quantity
        else:
            cash -= notion - float(trade.commission)
            held[trade.symbol] = current + trade.quantity
    return cash, {symbol: q for symbol, q in held.items() if q > 0}


def _marked(market_id: str, qty: dict[str, int], prices: dict[str, float]) -> float:
    total = 0.0
    for symbol, quantity in qty.items():
        price = _finite(prices.get(symbol))
        if price is None or quantity <= 0:
            continue
        total += _notional(market_id, symbol, quantity, price)
    return total


def build_overview(broker: PaperBroker) -> dict[str, Any]:
    now = broker.now()
    starts = _period_starts(now)
    accounts = broker.list_accounts()
    positions = broker.list_positions()
    trades = broker.list_trades()
    registry = broker.registry

    last_px: dict[tuple[str, str], float] = {}
    prev_px: dict[tuple[str, str], float] = {}
    frames: dict[tuple[str, str], pd.DataFrame] = {}

    symbols_needed: dict[str, set[str]] = {a.market_id: set() for a in accounts}
    for pos in positions:
        symbols_needed.setdefault(pos.market_id, set()).add(pos.symbol)
    for trade in trades:
        symbols_needed.setdefault(trade.market_id, set()).add(trade.symbol)

    jobs: list[tuple[str, str, Any]] = []
    for market_id, symbols in symbols_needed.items():
        try:
            adapter = registry.get(market_id)
        except KeyError:
            continue
        for symbol in symbols:
            jobs.append((market_id, symbol, adapter))

    def _job(item: tuple[str, str, Any]) -> tuple[str, str, pd.DataFrame | None]:
        market_id, symbol, adapter = item
        return market_id, symbol, _load_frame(adapter, symbol, now)

    workers = min(8, max(1, len(jobs)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        loaded = list(pool.map(_job, jobs)) if jobs else []
    for market_id, symbol, frame in loaded:
        if frame is not None:
            frames[(market_id, symbol)] = frame
        last, prev = _last_prev(frame)
        if last is not None:
            last_px[(market_id, symbol)] = last
        if prev is not None:
            prev_px[(market_id, symbol)] = prev

    books: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []

    for account in accounts:
        market_id = account.market_id
        qty_now = _qty_map(positions, market_id)
        now_prices = {s: last_px[(market_id, s)] for s in qty_now if (market_id, s) in last_px}
        invested = _marked(market_id, qty_now, now_prices)
        equity = float(account.cash) + invested
        book_pnls: dict[str, float] = {}
        for name, when in starts.items():
            cash_then, qty_then = _replay(account, qty_now, trades, when)
            then_prices: dict[str, float] = {}
            for symbol in qty_then:
                if when.date() == now.date() and (market_id, symbol) in prev_px:
                    then_prices[symbol] = prev_px[(market_id, symbol)]
                else:
                    close = _close_before(frames.get((market_id, symbol)), when)
                    if close is None:
                        close = last_px.get((market_id, symbol))
                    if close is not None:
                        then_prices[symbol] = close
            equity_then = cash_then + _marked(market_id, qty_then, then_prices)
            book_pnls[name] = equity - equity_then
        books.append(
            {
                "market_id": market_id,
                "currency": account.currency,
                "cash": float(account.cash),
                "invested": invested,
                "equity": equity,
                "initial_cash": float(account.initial_cash),
                "total_pnl": equity - float(account.initial_cash),
                "day_pnl": book_pnls["day"],
                "week_pnl": book_pnls["week"],
                "month_pnl": book_pnls["month"],
            }
        )

        for pos in positions:
            if pos.market_id != market_id:
                continue
            last = last_px.get((market_id, pos.symbol))
            prev = prev_px.get((market_id, pos.symbol))
            mult = multiplier(market_id, pos.symbol)
            cost = _notional(market_id, pos.symbol, pos.quantity, pos.avg_cost)
            marked = last is not None
            value = _notional(market_id, pos.symbol, pos.quantity, last) if marked else 0.0
            unrealized = (value - cost) if marked else None
            day_move = None
            if marked and prev is not None:
                day_move = _notional(market_id, pos.symbol, pos.quantity, last - prev)
            rows.append(
                {
                    "market_id": market_id,
                    "symbol": pos.symbol,
                    "quantity": int(pos.quantity),
                    "avg_cost": float(pos.avg_cost),
                    "last": last,
                    "prev_close": prev,
                    "multiplier": mult,
                    "asset_class": asset_class(market_id, pos.symbol),
                    "currency": account.currency,
                    "market_value": value,
                    "cost_value": cost,
                    "unrealized": unrealized,
                    "unrealized_pct": (unrealized / cost) if marked and cost else None,
                    "day_pnl": day_move,
                    "weight": (value / invested) if invested else 0.0,
                }
            )

    return {"asof": now.isoformat(), "books": books, "positions": rows}
