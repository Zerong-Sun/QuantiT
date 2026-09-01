"""Strategy base class and execution context."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from quantit.engine.broker import Broker, Order, OrderSide
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
    prices: dict[str, float] = field(default_factory=dict)
    bars: dict[str, pd.Series] = field(default_factory=dict)
    data_map: dict[str, pd.DataFrame] = field(default_factory=dict)

    @property
    def position(self) -> int:
        """Current position quantity (includes fills already applied this bar)."""
        pos = self.portfolio.get_position(self.symbol)
        return pos.quantity

    def position_of(self, symbol: str) -> int:
        """Quantity held in ``symbol``."""
        return self.portfolio.get_position(symbol).quantity

    def _signal_price(self, price: float | None, symbol: str | None = None) -> float:
        if price is not None:
            return price
        sym = symbol or self.symbol
        if self.prices and sym in self.prices:
            return float(self.prices[sym])
        if self.current_bar is not None and "close" in self.current_bar.index:
            return float(self.current_bar["close"])
        raise ValueError("No current bar to infer price from")

    def buy(self, quantity: int, price: float | None = None, symbol: str | None = None) -> Order:
        """Queue a buy. Fill price is set by the backtester, not ``price``."""
        order = Order(symbol=symbol or self.symbol, side=OrderSide.BUY, quantity=quantity)
        return self.broker.submit_order(order)

    def sell(self, quantity: int, price: float | None = None, symbol: str | None = None) -> Order:
        """Queue a sell. Fill price is set by the backtester, not ``price``."""
        order = Order(symbol=symbol or self.symbol, side=OrderSide.SELL, quantity=quantity)
        return self.broker.submit_order(order)

    def buy_pct(self, pct: float, price: float | None = None, symbol: str | None = None) -> Order | None:
        """Buy using a percentage of available cash (size estimated at signal price)."""
        sym = symbol or self.symbol
        px = self._signal_price(price, symbol=sym)
        cash = self.portfolio.cash
        qty = int((cash * pct) / px)
        if qty <= 0:
            return None
        return self.buy(qty, px, symbol=sym)

    def sell_all(self, price: float | None = None, symbol: str | None = None) -> Order | None:
        """Sell entire position in ``symbol`` (default: the context symbol)."""
        sym = symbol or self.symbol
        qty = self.position_of(sym)
        if qty <= 0:
            return None
        return self.sell(qty, price, symbol=sym)


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
