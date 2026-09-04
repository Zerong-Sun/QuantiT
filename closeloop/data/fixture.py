"""Synthetic CSI-like panel for tests (no pyqlib, no network)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from closeloop.data.protocol import DataPlane, panel_from_fields


class FixtureDataPlane(DataPlane):
    """Deterministic GBM-style prices for a handful of fake SH/SZ symbols."""

    def __init__(
        self,
        n_days: int = 80,
        n_instruments: int = 8,
        seed: int = 7,
        with_fundamentals: bool = True,
    ) -> None:
        rng = np.random.default_rng(seed)
        dates = pd.bdate_range("2020-01-02", periods=n_days, freq="C")
        instruments = tuple(
            f"SH{600000 + i}" if i < n_instruments // 2 else f"SZ{i - n_instruments // 2:06d}"
            for i in range(n_instruments)
        )
        close_levels = {}
        for j, inst in enumerate(instruments):
            shock = rng.normal(0.0004, 0.018, size=n_days)
            level = 10.0 * (1.0 + j * 0.3) * np.cumprod(1.0 + shock)
            close_levels[inst] = level
        close = pd.DataFrame(close_levels, index=dates)
        open_ = close.shift(1).fillna(close.iloc[0]) * (1.0 + rng.normal(0, 0.003, size=close.shape))
        high = np.maximum(open_, close) * (1.0 + rng.uniform(0.0, 0.012, size=close.shape))
        low = np.minimum(open_, close) * (1.0 - rng.uniform(0.0, 0.012, size=close.shape))
        volume = pd.DataFrame(
            rng.integers(800_000, 5_000_000, size=close.shape),
            index=dates,
            columns=close.columns,
            dtype=float,
        )
        vwap = (high + low + close) / 3.0
        packed = {
            "open": open_,
            "high": pd.DataFrame(high, index=dates, columns=close.columns),
            "low": pd.DataFrame(low, index=dates, columns=close.columns),
            "close": close,
            "volume": volume,
            "vwap": vwap,
        }
        if with_fundamentals:
            industry = pd.DataFrame(
                {inst: float(j % 3) for j, inst in enumerate(instruments)},
                index=dates,
            )
            packed["industry"] = industry
            packed["cap"] = close * volume
        self._panel = panel_from_fields(packed)
        self._instruments = instruments

    def calendar(self) -> pd.DatetimeIndex:
        return pd.DatetimeIndex(self._panel.index)

    def instruments(self) -> tuple[str, ...]:
        return self._instruments

    def load_panel(
        self,
        start: str,
        end: str,
        fields: tuple[str, ...] | None = None,
    ) -> pd.DataFrame:
        sl = self._panel.loc[start:end]
        if fields is None:
            return sl
        keep = [c for c in sl.columns if c[0] in fields]
        return sl.loc[:, keep]
