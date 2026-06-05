"""Technical indicator-based strategies."""

from __future__ import annotations

import pandas as pd

from quantit.engine.broker import OrderStatus
from quantit.strategy.base import Context, Strategy


class MACrossoverStrategy(Strategy):
    """Moving average crossover strategy.

    Buy when fast MA crosses above slow MA, sell when it crosses below.
    """

    def __init__(self, fast_period: int = 10, slow_period: int = 30, position_pct: float = 0.95) -> None:
        if fast_period >= slow_period:
            raise ValueError("fast_period must be less than slow_period")
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.position_pct = position_pct
        self._fast_ma: pd.Series | None = None
        self._slow_ma: pd.Series | None = None

    def on_start(self, context: Context) -> None:
        close = context.data["close"]
        self._fast_ma = close.rolling(self.fast_period).mean()
        self._slow_ma = close.rolling(self.slow_period).mean()
        context.indicators["fast_ma"] = self._fast_ma
        context.indicators["slow_ma"] = self._slow_ma

    def on_bar(self, context: Context, bar: pd.Series) -> None:
        if self._fast_ma is None or self._slow_ma is None:
            return

        date = context.current_date
        idx = context.data.index.get_loc(pd.Timestamp(date))

        if idx < self.slow_period:
            return

        fast_curr = self._fast_ma.iloc[idx]
        fast_prev = self._fast_ma.iloc[idx - 1]
        slow_curr = self._slow_ma.iloc[idx]
        slow_prev = self._slow_ma.iloc[idx - 1]

        if pd.isna(fast_curr) or pd.isna(slow_curr):
            return

        bullish_cross = fast_prev <= slow_prev and fast_curr > slow_curr
        bearish_cross = fast_prev >= slow_prev and fast_curr < slow_curr

        if bullish_cross and context.position == 0:
            context.buy_pct(self.position_pct)
        elif bearish_cross and context.position > 0:
            context.sell_all()
