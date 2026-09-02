"""Shared market data types for adapters and the paper terminal."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Quote:
    """Delayed last-sale quote derived from recent bars."""

    symbol: str
    market_id: str
    last: float
    open: float | None = None
    high: float | None = None
    low: float | None = None
    prev_close: float | None = None
    volume: float | None = None
    change: float | None = None
    change_pct: float | None = None
    timestamp: datetime | None = None
    delayed: bool = True


@dataclass(frozen=True)
class Instrument:
    """Tradable symbol metadata shown in the terminal."""

    symbol: str
    market_id: str
    name: str
    currency: str
    lot_size: int
    timezone: str
    session_hours: str
    asset_class: str = "equity"
    multiplier: int = 1
