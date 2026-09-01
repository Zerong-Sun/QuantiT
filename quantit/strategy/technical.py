"""Technical indicator-based strategies."""

from __future__ import annotations

import pandas as pd

from quantit.features.technical import RSIFeature, SMAFeature
from quantit.strategy.base import Context, Strategy


def _bar_index(context: Context) -> int:
    loc = context.data.index.get_loc(pd.Timestamp(context.current_date))
    if isinstance(loc, slice):
        return int(loc.start)
    if hasattr(loc, "__len__") and not isinstance(loc, (int, str)):
        return int(loc[0])
    return int(loc)


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
        self._fast_ma = SMAFeature(period=self.fast_period, name=f"sma_{self.fast_period}").compute(context.data)
        self._slow_ma = SMAFeature(period=self.slow_period, name=f"sma_{self.slow_period}").compute(context.data)
        context.indicators["fast_ma"] = self._fast_ma
        context.indicators["slow_ma"] = self._slow_ma

    def on_bar(self, context: Context, bar: pd.Series) -> None:
        if self._fast_ma is None or self._slow_ma is None:
            return

        idx = _bar_index(context)
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


class RSIMeanReversionStrategy(Strategy):
    """Buy when RSI is oversold, sell when it is overbought."""

    def __init__(
        self,
        period: int = 14,
        buy_threshold: float = 30,
        sell_threshold: float = 70,
        position_pct: float = 0.95,
    ) -> None:
        self.period = period
        self.buy_threshold = buy_threshold
        self.sell_threshold = sell_threshold
        self.position_pct = position_pct
        self._rsi: pd.Series | None = None

    def on_start(self, context: Context) -> None:
        name = f"rsi_{self.period}"
        self._rsi = RSIFeature(period=self.period, name=name).compute(context.data)
        context.indicators[name] = self._rsi

    def on_bar(self, context: Context, bar: pd.Series) -> None:
        if self._rsi is None:
            return
        idx = _bar_index(context)
        val = self._rsi.iloc[idx]
        if pd.isna(val):
            return

        if val < self.buy_threshold and context.position == 0:
            context.buy_pct(self.position_pct)
        elif val > self.sell_threshold and context.position > 0:
            context.sell_all()
