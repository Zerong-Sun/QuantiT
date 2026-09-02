"""US paper-book strategy: trend MA in uptrends, RSI only in downtrends."""

from __future__ import annotations

import pandas as pd

from quantit.features.technical import RSIFeature, SMAFeature
from quantit.strategy.base import Context, Strategy
from quantit.strategy.signals import resolve_us_book_action
from quantit.strategy.technical import _bar_index, ma_cross_side, rsi_reversion_side


class USBookStrategy(Strategy):
    """Same rules as paper ``resolve_us_book_action``.

    Uptrend (fast SMA > slow SMA): buy if flat, including already-in-trend.
    Death-cross sell always wins. Downtrend: RSI oversold/overbought only.
    """

    def __init__(
        self,
        fast_period: int = 10,
        slow_period: int = 30,
        period: int = 14,
        buy_threshold: float = 30,
        sell_threshold: float = 70,
        position_pct: float = 0.95,
    ) -> None:
        if fast_period >= slow_period:
            raise ValueError("fast_period must be less than slow_period")
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.period = period
        self.buy_threshold = buy_threshold
        self.sell_threshold = sell_threshold
        self.position_pct = position_pct
        self._fast_ma: pd.Series | None = None
        self._slow_ma: pd.Series | None = None
        self._rsi: pd.Series | None = None

    def on_start(self, context: Context) -> None:
        self._fast_ma = SMAFeature(period=self.fast_period, name=f"sma_{self.fast_period}").compute(context.data)
        self._slow_ma = SMAFeature(period=self.slow_period, name=f"sma_{self.slow_period}").compute(context.data)
        self._rsi = RSIFeature(period=self.period, name=f"rsi_{self.period}").compute(context.data)
        context.indicators["fast_ma"] = self._fast_ma
        context.indicators["slow_ma"] = self._slow_ma
        context.indicators[f"rsi_{self.period}"] = self._rsi

    def action_for_bar(self, idx: int, fast: pd.Series, slow: pd.Series, rsi: pd.Series) -> str:
        """Return buy/sell/hold for bar ``idx`` using paper book rules."""
        if idx < 1 or idx >= len(fast):
            return "hold"
        fast_curr = fast.iloc[idx]
        slow_curr = slow.iloc[idx]
        fast_prev = fast.iloc[idx - 1]
        slow_prev = slow.iloc[idx - 1]
        rsi_val = rsi.iloc[idx]
        if pd.isna(fast_curr) or pd.isna(slow_curr) or pd.isna(fast_prev) or pd.isna(slow_prev):
            return "hold"
        ma_side = ma_cross_side(float(fast_prev), float(slow_prev), float(fast_curr), float(slow_curr))
        rsi_side = rsi_reversion_side(float(rsi_val), self.buy_threshold, self.sell_threshold)
        ma = {
            "action": ma_side or "hold",
            "reason": "crossed below" if ma_side == "sell" else ("crossed above" if ma_side == "buy" else "hold"),
            "values": {"fast_ma": float(fast_curr), "slow_ma": float(slow_curr)},
        }
        rsi_d = {
            "action": rsi_side or "hold",
            "reason": "oversold" if rsi_side == "buy" else ("overbought" if rsi_side == "sell" else "hold"),
            "values": {"rsi": float(rsi_val) if not pd.isna(rsi_val) else None},
        }
        return resolve_us_book_action(ma, rsi_d)["action"]

    def on_bar(self, context: Context, bar: pd.Series) -> None:
        if self._fast_ma is None or self._slow_ma is None or self._rsi is None:
            return
        idx = _bar_index(context)
        if idx < self.slow_period:
            return
        side = self.action_for_bar(idx, self._fast_ma, self._slow_ma, self._rsi)
        if side == "buy" and context.position == 0:
            context.buy_pct(self.position_pct)
        elif side == "sell" and context.position > 0:
            context.sell_all()
