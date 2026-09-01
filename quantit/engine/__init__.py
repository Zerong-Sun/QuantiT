from quantit.engine.broker import Broker, Order, OrderSide, OrderStatus
from quantit.engine.portfolio import Portfolio, Position

# Lazy Backtester import: strategy.base imports engine.broker, which would
# otherwise load backtester and re-enter strategy.base (circular).

__all__ = [
    "Backtester",
    "BacktestResult",
    "Broker",
    "Order",
    "OrderSide",
    "OrderStatus",
    "Portfolio",
    "Position",
]


def __getattr__(name: str):
    if name in {"Backtester", "BacktestResult"}:
        from quantit.engine.backtester import BacktestResult, Backtester

        return Backtester if name == "Backtester" else BacktestResult
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
