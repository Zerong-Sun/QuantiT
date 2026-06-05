"""Strategy base class and execution context."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from quantit.engine.broker import Broker, Order
from quantit.engine.portfolio import Portfolio


@dataclass
class Context:
    """Runtime context passed to strategy hooks."""

    portfolio: Portfolio
    broker: Broker
    symbol: str
    data: pd.DataFrame
    current_date: datetime | None = None
    current_bar: pd.Series | None = None
    indicators: dict[str, pd.Series] = field(default_factory=dict)
    extra: dict = field(default_factory=dict)

    @property
    def position(self) -> int:
        """Current position quantity."""
        pos = self.portfolio.get_position(self.symbol)
        return pos.quantity

    def buy(self, quantity: int, price: float | None = None) -> Order:
        """Place a buy order."""
        if price is None:
            price = float(self.current_bar["close"])
        return self.broker.buy(self.symbol, quantity, price, self.current_date)

    def sell(self, quantity: int, price: float | None = None) -> Order:
        """Place a sell order."""
        if price is None:
            price = float(self.current_bar["close"])
        return self.broker.sell(self.symbol, quantity, price, self.current_date)

    def buy_pct(self, pct: float, price: float | None = None) -> Order | None:
        """Buy using a percentage of available cash."""
        if price is None:
            price = float(self.current_bar["close"])
        cash = self.portfolio.cash
        qty = int((cash * pct) / price)
        if qty <= 0:
            return None
        return self.buy(qty, price)

    def sell_all(self, price: float | None = None) -> Order | None:
        """Sell entire position."""
        qty = self.position
        if qty <= 0:
            return None
        return self.sell(qty, price)


class Strategy(ABC):
    """Base class for all trading strategies."""

    def on_start(self, context: Context) -> None:
        """Called once before backtest begins."""

    @abstractmethod
    def on_bar(self, context: Context, bar: pd.Series) -> None:
        """Called on each new bar."""

    def on_order(self, context: Context, order: Order) -> None:
        """Called when an order is filled."""

    def on_end(self, context: Context) -> None:
        """Called once after backtest ends."""
