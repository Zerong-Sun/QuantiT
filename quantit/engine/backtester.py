"""Event-driven backtesting engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from quantit.engine.broker import Broker, Order, Trade
from quantit.engine.portfolio import Portfolio
from quantit.strategy.base import Context, Strategy
from quantit.utils.config import get_config


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
    """Event-driven backtester that iterates bar-by-bar."""

    def __init__(
        self,
        initial_cash: float | None = None,
        commission_rate: float | None = None,
        slippage_rate: float | None = None,
    ) -> None:
        config = get_config()
        self.initial_cash = initial_cash if initial_cash is not None else config.initial_cash
        self.commission_rate = commission_rate
        self.slippage_rate = slippage_rate

    def run(
        self,
        strategy: Strategy,
        data: pd.DataFrame,
        symbol: str = "UNKNOWN",
    ) -> BacktestResult:
        """Run backtest on OHLCV data."""
        if data.empty:
            raise ValueError("Cannot backtest with empty data")

        data = data.sort_index()
        portfolio = Portfolio(initial_cash=self.initial_cash)
        broker = Broker(
            portfolio,
            commission_rate=self.commission_rate,
            slippage_rate=self.slippage_rate,
        )
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
            prices = {symbol: float(bar["close"])}
            portfolio.record(context.current_date, prices)
            strategy.on_bar(context, bar)

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
