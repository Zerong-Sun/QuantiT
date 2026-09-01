"""Event-driven backtesting engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from quantit.engine.broker import Broker, Order, OrderStatus, Trade
from quantit.engine.portfolio import Portfolio
from quantit.strategy.base import Context, Strategy
from quantit.utils.config import get_config


def _session_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Naive, normalized daily index so HK and US timestamps align on calendar dates."""
    out = df.copy()
    idx = pd.DatetimeIndex(pd.to_datetime(out.index))
    if idx.tz is not None:
        idx = idx.tz_convert("UTC").tz_localize(None)
    out.index = idx.normalize()
    out = out[~out.index.duplicated(keep="last")]
    return out.sort_index()


@dataclass
class BacktestResult:
    """Results from a backtest run."""

    equity_curve: pd.Series
    trades: list[Trade]
    portfolio: Portfolio
    symbol: str
    start: datetime
    end: datetime
    metrics: dict[str, float] = field(default_factory=dict)


class Backtester:
    """Event-driven backtester that iterates bar-by-bar.

    Default fill policy is ``next_open``: a signal on bar t fills at bar t+1 open.
    Pass ``fill_on="same_close"`` to fill at the signal bar's close (legacy).
    Unfilled orders on the last bar are cancelled.
    """

    def __init__(
        self,
        initial_cash: float | None = None,
        commission_rate: float | None = None,
        slippage_rate: float | None = None,
        fill_on: str | None = None,
    ) -> None:
        config = get_config()
        self.initial_cash = initial_cash if initial_cash is not None else config.initial_cash
        self.commission_rate = commission_rate
        self.slippage_rate = slippage_rate
        self.fill_on = fill_on if fill_on is not None else config.fill_on
        if self.fill_on not in {"next_open", "same_close"}:
            raise ValueError("fill_on must be 'next_open' or 'same_close'")

    def _notify_fills(self, strategy: Strategy, context: Context, orders: list[Order]) -> None:
        for order in orders:
            if order.status == OrderStatus.FILLED:
                strategy.on_order(context, order)

    def run(
        self,
        strategy: Strategy,
        data: pd.DataFrame | dict[str, pd.DataFrame],
        symbol: str = "UNKNOWN",
    ) -> BacktestResult:
        """Run backtest on OHLCV data (single name or a symbol → frame map)."""
        if isinstance(data, dict):
            return self._run_multi(strategy, data, name=symbol)
        return self._run_single(strategy, data, symbol=symbol)

    def _make_broker(self, portfolio: Portfolio) -> Broker:
        return Broker(
            portfolio,
            commission_rate=self.commission_rate,
            slippage_rate=self.slippage_rate,
            fill_on=self.fill_on,
        )

    def _run_single(
        self,
        strategy: Strategy,
        data: pd.DataFrame,
        symbol: str,
    ) -> BacktestResult:
        if data.empty:
            raise ValueError("Cannot backtest with empty data")
        if "open" not in data.columns or "close" not in data.columns:
            raise ValueError("OHLCV data must include 'open' and 'close' columns")

        data = data.sort_index()
        portfolio = Portfolio(initial_cash=self.initial_cash)
        broker = self._make_broker(portfolio)
        context = Context(
            portfolio=portfolio,
            broker=broker,
            symbol=symbol,
            data=data,
        )

        strategy.on_start(context)

        for date, bar in data.iterrows():
            context.current_date = pd.Timestamp(date).to_pydatetime()
            context.current_bar = bar
            context.prices = {symbol: float(bar["close"])}
            ts = context.current_date

            if self.fill_on == "next_open":
                filled = broker.fill_pending({symbol: float(bar["open"])}, ts)
                self._notify_fills(strategy, context, filled)

            prices = {symbol: float(bar["close"])}
            context.prices = prices
            portfolio.record(ts, prices)
            strategy.on_bar(context, bar)

            if self.fill_on == "same_close":
                filled = broker.fill_pending({symbol: float(bar["close"])}, ts)
                self._notify_fills(strategy, context, filled)

        broker.cancel_pending()
        strategy.on_end(context)

        equity = portfolio.equity_curve()
        return BacktestResult(
            equity_curve=equity,
            trades=broker.trades,
            portfolio=portfolio,
            symbol=symbol,
            start=pd.Timestamp(data.index[0]).to_pydatetime(),
            end=pd.Timestamp(data.index[-1]).to_pydatetime(),
        )

    def _run_multi(
        self,
        strategy: Strategy,
        data: dict[str, pd.DataFrame],
        name: str,
    ) -> BacktestResult:
        frames = {
            sym: _session_frame(df)
            for sym, df in data.items()
            if df is not None and not df.empty
        }
        if not frames:
            raise ValueError("Cannot backtest with empty data")
        for sym, df in frames.items():
            if "open" not in df.columns or "close" not in df.columns:
                raise ValueError(f"OHLCV data for {sym} must include 'open' and 'close' columns")

        calendar = None
        for df in frames.values():
            calendar = df.index if calendar is None else calendar.union(df.index)
        calendar = calendar.sort_values()

        portfolio = Portfolio(initial_cash=self.initial_cash)
        broker = self._make_broker(portfolio)
        dummy = next(iter(frames.values()))
        context = Context(
            portfolio=portfolio,
            broker=broker,
            symbol=name,
            data=dummy,
            data_map=frames,
        )

        last_open: dict[str, float] = {}
        last_close: dict[str, float] = {}
        last_bar: dict[str, pd.Series] = {}

        strategy.on_start(context)

        for date in calendar:
            ts = pd.Timestamp(date).to_pydatetime()
            session_opens: dict[str, float] = {}
            session_closes: dict[str, float] = {}
            session_bars: dict[str, pd.Series] = {}
            for sym, df in frames.items():
                if date in df.index:
                    bar = df.loc[date]
                    last_open[sym] = float(bar["open"])
                    last_close[sym] = float(bar["close"])
                    last_bar[sym] = bar
                    session_opens[sym] = last_open[sym]
                    session_closes[sym] = last_close[sym]
                    session_bars[sym] = bar
                elif sym in last_close:
                    session_closes[sym] = last_close[sym]
                    if sym in last_bar:
                        session_bars[sym] = last_bar[sym]

            context.current_date = ts
            context.prices = dict(session_closes)
            context.bars = session_bars
            context.current_bar = next(iter(session_bars.values()), None)

            if self.fill_on == "next_open":
                filled = broker.fill_pending(session_opens, ts)
                self._notify_fills(strategy, context, filled)

            portfolio.record(ts, session_closes)
            dummy_bar = context.current_bar if context.current_bar is not None else pd.Series(dtype=float)
            strategy.on_bar(context, dummy_bar)

            if self.fill_on == "same_close":
                filled = broker.fill_pending(session_closes, ts)
                self._notify_fills(strategy, context, filled)

        broker.cancel_pending()
        strategy.on_end(context)

        equity = portfolio.equity_curve()
        return BacktestResult(
            equity_curve=equity,
            trades=broker.trades,
            portfolio=portfolio,
            symbol=name,
            start=pd.Timestamp(calendar[0]).to_pydatetime(),
            end=pd.Timestamp(calendar[-1]).to_pydatetime(),
        )
