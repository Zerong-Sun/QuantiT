"""Next-bar fill and on_order tests."""

from __future__ import annotations

import pandas as pd

from quantit.engine.backtester import Backtester
from quantit.engine.broker import Order, OrderStatus
from quantit.strategy.base import Context, Strategy


def _ohlcv() -> pd.DataFrame:
    dates = pd.date_range("2020-01-01", periods=4, freq="D")
    return pd.DataFrame(
        {
            "open": [100.0, 110.0, 120.0, 130.0],
            "high": [101.0, 111.0, 121.0, 131.0],
            "low": [99.0, 109.0, 119.0, 129.0],
            "close": [105.0, 115.0, 125.0, 135.0],
            "volume": [1_000] * 4,
        },
        index=dates,
    )


class BuyOnceStrategy(Strategy):
    """Buy 1 share on the first bar only."""

    def __init__(self) -> None:
        self.fills: list[Order] = []
        self.bought = False

    def on_bar(self, context: Context, bar: pd.Series) -> None:
        if not self.bought:
            context.buy(1)
            self.bought = True

    def on_order(self, context: Context, order: Order) -> None:
        self.fills.append(order)


class BuyLastBarStrategy(Strategy):
    """Buy only on the last bar so the order should be cancelled."""

    def on_bar(self, context: Context, bar: pd.Series) -> None:
        if pd.Timestamp(context.current_date) == pd.Timestamp(context.data.index[-1]):
            context.buy(1)


def test_next_open_fill_not_same_bar() -> None:
    data = _ohlcv()
    strategy = BuyOnceStrategy()
    result = Backtester(initial_cash=10_000, commission_rate=0.0, slippage_rate=0.0).run(
        strategy, data, symbol="TEST"
    )

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.timestamp == data.index[1].to_pydatetime()
    assert trade.price == 110.0
    assert len(strategy.fills) == 1
    assert strategy.fills[0].status == OrderStatus.FILLED
    assert strategy.fills[0].fill_price == 110.0

    first_day = result.portfolio.history[0]
    assert first_day.equity == 10_000
    assert first_day.positions == {}


def test_same_close_fills_signal_bar() -> None:
    data = _ohlcv()
    strategy = BuyOnceStrategy()
    result = Backtester(
        initial_cash=10_000,
        commission_rate=0.0,
        slippage_rate=0.0,
        fill_on="same_close",
    ).run(strategy, data, symbol="TEST")

    assert len(result.trades) == 1
    assert result.trades[0].timestamp == data.index[0].to_pydatetime()
    assert result.trades[0].price == 105.0
    assert len(strategy.fills) == 1


def test_last_bar_order_is_cancelled() -> None:
    data = _ohlcv()
    result = Backtester(initial_cash=10_000, commission_rate=0.0, slippage_rate=0.0).run(
        BuyLastBarStrategy(), data, symbol="TEST"
    )
    assert result.trades == []
    assert result.portfolio.cash == 10_000
