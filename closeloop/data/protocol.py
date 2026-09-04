"""Qlib-shaped data plane contract for A-share CSI300.

Panel layout
------------
index: DatetimeIndex (name ``datetime``)
columns: MultiIndex levels ``("field", "instrument")``
fields: open, high, low, close, volume, vwap  (+ optional returns)

US Yahoo / paper MarketAdapter paths are out of scope.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

import pandas as pd

DEFAULT_FIELDS: tuple[str, ...] = ("open", "high", "low", "close", "volume", "vwap")


def default_data_dir() -> Path:
    import os

    override = os.environ.get("CLOSELOOP_DATA_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".quantit" / "closeloop" / "qlib_cn"


class DataPlane(ABC):
    """Calendar + instruments + OHLCV panel. A-share only."""

    @abstractmethod
    def calendar(self) -> pd.DatetimeIndex:
        """Trading-day index (join key)."""

    @abstractmethod
    def instruments(self) -> tuple[str, ...]:
        """Universe membership (Qlib-style symbols, e.g. SH600000)."""

    @abstractmethod
    def load_panel(
        self,
        start: str,
        end: str,
        fields: tuple[str, ...] | None = None,
    ) -> pd.DataFrame:
        """Return a field×instrument panel. ``fields=None`` keeps every stored field."""


def field_frame(panel: pd.DataFrame, field: str) -> pd.DataFrame:
    """Dates × instruments for one field."""
    if not isinstance(panel.columns, pd.MultiIndex):
        raise TypeError("panel columns must be MultiIndex(field, instrument)")
    return panel[field].copy()


def panel_from_fields(fields: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Build a panel from {field: dates×instruments} frames."""
    pieces = []
    for name, frame in fields.items():
        col = frame.copy()
        col.columns = pd.MultiIndex.from_product([[name], col.columns], names=["field", "instrument"])
        pieces.append(col)
    panel = pd.concat(pieces, axis=1)
    panel.index = pd.DatetimeIndex(panel.index, name="datetime")
    panel = panel.sort_index(axis=1)
    return panel


def add_returns(panel: pd.DataFrame) -> pd.DataFrame:
    """Append close-to-close returns without lookahead (first row NaN)."""
    close = field_frame(panel, "close")
    ret = close.pct_change()
    ret.columns = pd.MultiIndex.from_product([["returns"], ret.columns], names=["field", "instrument"])
    out = pd.concat([panel, ret], axis=1).sort_index(axis=1)
    out.index = pd.DatetimeIndex(out.index, name="datetime")
    return out
