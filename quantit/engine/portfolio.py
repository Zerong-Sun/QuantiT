"""Portfolio state tracking."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd


@dataclass
class Position:
    """A single position in a symbol."""

    symbol: str
    quantity: int = 0
    avg_cost: float = 0.0

    @property
    def market_value(self) -> float:
        return self.quantity * self.avg_cost

    def update_buy(self, quantity: int, price: float) -> None:
        total_cost = self.avg_cost * self.quantity + price * quantity
        self.quantity += quantity
        if self.quantity > 0:
            self.avg_cost = total_cost / self.quantity

    def update_sell(self, quantity: int) -> None:
        if quantity > self.quantity:
            raise ValueError(f"Cannot sell {quantity} shares, only {self.quantity} held")
        self.quantity -= quantity
        if self.quantity == 0:
            self.avg_cost = 0.0


@dataclass
class PortfolioSnapshot:
    """Point-in-time portfolio state."""

    date: datetime
    cash: float
    equity: float
    positions: dict[str, int]


@dataclass
class Portfolio:
    """Track cash, positions, and equity over time."""

    initial_cash: float
    cash: float = field(init=False)
    positions: dict[str, Position] = field(default_factory=dict)
    history: list[PortfolioSnapshot] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.cash = self.initial_cash

    def get_position(self, symbol: str) -> Position:
        if symbol not in self.positions:
            self.positions[symbol] = Position(symbol=symbol)
        return self.positions[symbol]

    def buy(self, symbol: str, quantity: int, price: float, commission: float = 0.0) -> float:
        """Execute a buy. Returns total cost."""
        cost = price * quantity + commission
        if cost > self.cash:
            raise ValueError(f"Insufficient cash: need {cost:.2f}, have {self.cash:.2f}")
        self.cash -= cost
        pos = self.get_position(symbol)
        pos.update_buy(quantity, price)
        return cost

    def sell(self, symbol: str, quantity: int, price: float, commission: float = 0.0) -> float:
        """Execute a sell. Returns proceeds."""
        pos = self.get_position(symbol)
        if quantity > pos.quantity:
            raise ValueError(f"Insufficient shares: need {quantity}, have {pos.quantity}")
        proceeds = price * quantity - commission
        pos.update_sell(quantity)
        self.cash += proceeds
        return proceeds

    def equity(self, prices: dict[str, float]) -> float:
        """Total portfolio value."""
        holdings = sum(
            pos.quantity * prices.get(sym, pos.avg_cost)
            for sym, pos in self.positions.items()
            if pos.quantity > 0
        )
        return self.cash + holdings

    def record(self, date: datetime, prices: dict[str, float]) -> None:
        """Record a snapshot."""
        self.history.append(
            PortfolioSnapshot(
                date=date,
                cash=self.cash,
                equity=self.equity(prices),
                positions={s: p.quantity for s, p in self.positions.items() if p.quantity > 0},
            )
        )

    def equity_curve(self) -> pd.Series:
        """Return equity history as a Series."""
        if not self.history:
            return pd.Series(dtype=float)
        return pd.Series(
            {s.date: s.equity for s in self.history},
            name="equity",
        ).sort_index()
