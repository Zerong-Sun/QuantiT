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
    """Simulated broker with commission and slippage."""

    def __init__(
        self,
        portfolio: Portfolio,
        commission_rate: float | None = None,
        slippage_rate: float | None = None,
    ) -> None:
        config = get_config()
        self.portfolio = portfolio
        self.commission_rate = commission_rate if commission_rate is not None else config.commission_rate
        self.slippage_rate = slippage_rate if slippage_rate is not None else config.slippage_rate
        self.trades: list[Trade] = []
        self.pending_orders: list[Order] = []

    def submit_order(self, order: Order, price: float, timestamp: datetime) -> Order:
        """Submit and immediately fill a market order at the given price."""
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

    def buy(self, symbol: str, quantity: int, price: float, timestamp: datetime) -> Order:
        """Convenience method to buy."""
        order = Order(symbol=symbol, side=OrderSide.BUY, quantity=quantity)
        return self.submit_order(order, price, timestamp)

    def sell(self, symbol: str, quantity: int, price: float, timestamp: datetime) -> Order:
        """Convenience method to sell."""
        order = Order(symbol=symbol, side=OrderSide.SELL, quantity=quantity)
        return self.submit_order(order, price, timestamp)
