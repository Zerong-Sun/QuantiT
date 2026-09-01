"""Simulated broker for backtesting."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from uuid import uuid4

from quantit.engine.portfolio import Portfolio
from quantit.utils.config import get_config


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


class OrderStatus(Enum):
    PENDING = "pending"
    FILLED = "filled"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


@dataclass
class Order:
    """A trade order."""

    symbol: str
    side: OrderSide
    quantity: int
    order_id: str = field(default_factory=lambda: str(uuid4())[:8])
    status: OrderStatus = OrderStatus.PENDING
    fill_price: float = 0.0
    commission: float = 0.0
    fill_time: datetime | None = None


@dataclass
class Trade:
    """A completed trade record."""

    order_id: str
    symbol: str
    side: OrderSide
    quantity: int
    price: float
    commission: float
    timestamp: datetime


class Broker:
    """Simulated broker with commission and slippage.

    Market orders are queued and filled by ``fill_pending``. The backtester
    decides whether that happens on the next bar's open or the same bar's close.
    """

    def __init__(
        self,
        portfolio: Portfolio,
        commission_rate: float | None = None,
        slippage_rate: float | None = None,
        fill_on: str | None = None,
    ) -> None:
        config = get_config()
        self.portfolio = portfolio
        self.commission_rate = commission_rate if commission_rate is not None else config.commission_rate
        self.slippage_rate = slippage_rate if slippage_rate is not None else config.slippage_rate
        self.fill_on = fill_on if fill_on is not None else config.fill_on
        self.trades: list[Trade] = []
        self.pending_orders: list[Order] = []

    def _fill(self, order: Order, price: float, timestamp: datetime) -> Order:
        if order.quantity <= 0:
            order.status = OrderStatus.REJECTED
            return order

        slip = price * self.slippage_rate
        fill_price = price + slip if order.side == OrderSide.BUY else price - slip
        commission = fill_price * order.quantity * self.commission_rate

        try:
            if order.side == OrderSide.BUY:
                self.portfolio.buy(order.symbol, order.quantity, fill_price, commission)
            else:
                self.portfolio.sell(order.symbol, order.quantity, fill_price, commission)
        except ValueError:
            order.status = OrderStatus.REJECTED
            return order

        order.status = OrderStatus.FILLED
        order.fill_price = fill_price
        order.commission = commission
        order.fill_time = timestamp

        self.trades.append(
            Trade(
                order_id=order.order_id,
                symbol=order.symbol,
                side=order.side,
                quantity=order.quantity,
                price=fill_price,
                commission=commission,
                timestamp=timestamp,
            )
        )
        return order

    def submit_order(self, order: Order) -> Order:
        """Queue a market order for later fill."""
        if order.quantity <= 0:
            order.status = OrderStatus.REJECTED
            return order
        order.status = OrderStatus.PENDING
        self.pending_orders.append(order)
        return order

    def fill_pending(self, prices: dict[str, float], timestamp: datetime) -> list[Order]:
        """Fill queued orders at the given per-symbol prices."""
        filled: list[Order] = []
        remaining: list[Order] = []
        for order in self.pending_orders:
            price = prices.get(order.symbol)
            if price is None:
                remaining.append(order)
                continue
            result = self._fill(order, price, timestamp)
            filled.append(result)
        self.pending_orders = remaining
        return filled

    def cancel_pending(self) -> None:
        """Cancel all unfilled orders (used at end of backtest)."""
        for order in self.pending_orders:
            order.status = OrderStatus.CANCELLED
        self.pending_orders.clear()

    def buy(self, symbol: str, quantity: int, price: float | None = None, timestamp: datetime | None = None) -> Order:
        """Place a buy. Fills immediately only when price and timestamp are given (same-close tests)."""
        order = Order(symbol=symbol, side=OrderSide.BUY, quantity=quantity)
        if price is not None and timestamp is not None:
            return self._fill(order, price, timestamp)
        return self.submit_order(order)

    def sell(self, symbol: str, quantity: int, price: float | None = None, timestamp: datetime | None = None) -> Order:
        """Place a sell. Fills immediately only when price and timestamp are given (same-close tests)."""
        order = Order(symbol=symbol, side=OrderSide.SELL, quantity=quantity)
        if price is not None and timestamp is not None:
            return self._fill(order, price, timestamp)
        return self.submit_order(order)
