"""Time-series momentum with volatility targeting (long only)."""

from __future__ import annotations

import math

import pandas as pd

from quantit.features.technical import VolatilityFeature
from quantit.strategy.base import Context, Strategy
from quantit.strategy.technical import _bar_index


def tsmom_momentum(close: pd.Series, lookback: int, skip: int) -> pd.Series:
    """Return from ``t-lookback`` to ``t-skip`` (skip=0 uses the latest close)."""
    if lookback <= 0:
        raise ValueError("lookback must be positive")
    if skip < 0:
        raise ValueError("skip must be >= 0")
    if skip >= lookback:
        raise ValueError("skip must be less than lookback")
    if skip == 0:
        return close.pct_change(lookback)
    return close.shift(skip).pct_change(lookback - skip)


def tsmom_size(
    equity: float,
    price: float,
    realized_vol: float,
    target_vol: float,
    vol_floor: float,
    max_position_pct: float,
) -> int:
    """Shares so notional vol matches ``target_vol``, capped by cash fraction."""
    if equity <= 0 or price <= 0:
        return 0
    if not math.isfinite(realized_vol) or not math.isfinite(target_vol) or not math.isfinite(price):
        return 0
    denom = max(float(realized_vol), float(vol_floor), 1e-8)
    if not math.isfinite(denom) or denom <= 0:
        return 0
    gross = float(target_vol) / denom
    pct = min(max(gross, 0.0), float(max_position_pct))
    if not math.isfinite(pct) or pct <= 0:
        return 0
    return int(equity * pct / price)


def coerce_vol(value: object, default: float = 0.15) -> float:
    """Parse a vol number; NaN/None/non-finite fall back to ``default``."""
    try:
        vol = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    if not math.isfinite(vol) or vol <= 0:
        return default
    return vol


class TSMOMStrategy(Strategy):
    """Long when skipped lookback return is positive; size by realized vol.

    Cash when momentum is non-positive. No shorting.
    """

    def __init__(
        self,
        lookback: int = 252,
        skip: int = 21,
        target_vol: float = 0.15,
        vol_lookback: int = 20,
        vol_floor: float = 0.05,
        max_position_pct: float = 0.95,
        rebalance_band: float = 0.10,
    ) -> None:
        if lookback <= 0:
            raise ValueError("lookback must be positive")
        if skip < 0:
            raise ValueError("skip must be >= 0")
        if skip >= lookback:
            raise ValueError("skip must be less than lookback")
        self.lookback = lookback
        self.skip = skip
        self.target_vol = target_vol
        self.vol_lookback = vol_lookback
        self.vol_floor = vol_floor
        self.max_position_pct = max_position_pct
        self.rebalance_band = rebalance_band
        self._mom: pd.Series | None = None
        self._vol: pd.Series | None = None

    def on_start(self, context: Context) -> None:
        close = context.data["close"]
        self._mom = tsmom_momentum(close, self.lookback, self.skip)
        self._vol = VolatilityFeature(period=self.vol_lookback).compute(context.data)
        context.indicators["tsmom"] = self._mom
        context.indicators["realized_vol"] = self._vol

    def on_bar(self, context: Context, bar: pd.Series) -> None:
        if self._mom is None or self._vol is None:
            return
        idx = _bar_index(context)
        need = max(self.lookback, self.vol_lookback) + 1
        if idx < need:
            return
        mom = self._mom.iloc[idx]
        vol = self._vol.iloc[idx]
        if pd.isna(mom) or pd.isna(vol):
            return
        price = float(bar["close"]) if "close" in bar.index else context._signal_price(None)
        if float(mom) <= 0:
            if context.position > 0:
                context.sell_all()
            return
        equity = context.portfolio.equity(context.prices) if context.prices else context.portfolio.cash
        target = tsmom_size(
            equity=float(equity),
            price=price,
            realized_vol=float(vol),
            target_vol=self.target_vol,
            vol_floor=self.vol_floor,
            max_position_pct=self.max_position_pct,
        )
        affordable = int(context.portfolio.cash / price) if price > 0 else 0
        held = context.position
        if held <= 0:
            qty = min(target, affordable)
            if qty > 0:
                context.buy(qty)
            return
        if target <= 0:
            context.sell_all()
            return
        delta = target - held
        if abs(delta) / held <= self.rebalance_band:
            return
        if delta > 0:
            extra = min(delta, affordable)
            if extra > 0:
                context.buy(extra)
        else:
            context.sell(-delta)
