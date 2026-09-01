"""Base market adapter: venue rules plus delayed bars/quotes."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Protocol

import pandas as pd

from quantit.data.provider import DataProvider, YahooFinanceProvider
from quantit.markets.base import MarketProfile
from quantit.markets.types import Instrument, Quote


class QuoteFeed(Protocol):
    """Read delayed or live quotes. Adapters implement this; a WebSocket feed can later."""

    def fetch_quote(self, symbol: str) -> Quote:
        ...


class MarketAdapter(ABC):
    """Plugin surface for a trading venue.

    New markets register an adapter; API routes stay unchanged.
    """

    market_id: str
    profile: MarketProfile
    timezone: str
    session_hours: str
    t_plus: int = 0
    supported_intervals: tuple[str, ...] = ("1d", "1h", "5m")

    def __init__(self, provider: DataProvider | None = None) -> None:
        self.provider = provider if provider is not None else self.default_provider()

    def default_provider(self) -> DataProvider:
        return YahooFinanceProvider()

    @abstractmethod
    def normalize_symbol(self, raw: str) -> str:
        """Return the canonical symbol used with the data provider."""

    def lot_size(self, symbol: str) -> int:
        """Board lot. ``0`` means the venue has lots but they are not enforced."""
        return 1

    def validate_quantity(self, symbol: str, quantity: int) -> list[str]:
        """Return human-readable errors; empty list means the size is valid."""
        if quantity <= 0:
            return ["quantity must be positive"]
        lot = self.lot_size(self.normalize_symbol(symbol))
        if lot > 1 and quantity % lot != 0:
            return [f"quantity must be a multiple of {lot}"]
        return []

    def universe(self) -> dict[str, str]:
        """Canonical symbol -> display name for search."""
        return {}

    def fetch_bars(
        self,
        symbol: str,
        interval: str,
        start: str | datetime,
        end: str | datetime,
    ) -> pd.DataFrame:
        if interval not in self.supported_intervals:
            raise ValueError(f"Unsupported interval {interval!r} for market {self.market_id}")
        canonical = self.normalize_symbol(symbol)
        return self.provider.fetch(canonical, start, end, interval)

    def fetch_quote(self, symbol: str) -> Quote:
        canonical = self.normalize_symbol(symbol)
        end = pd.Timestamp.utcnow().normalize() + pd.Timedelta(days=1)
        start = end - pd.Timedelta(days=14)
        df = self.fetch_bars(canonical, "1d", start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
        if df is None or df.empty:
            raise ValueError(f"No quote for {canonical}")
        last = df.iloc[-1]
        last_px = float(last["close"])
        prev_close = float(df.iloc[-2]["close"]) if len(df) > 1 else last_px
        change = last_px - prev_close
        change_pct = (change / prev_close * 100.0) if prev_close else 0.0
        ts = pd.Timestamp(df.index[-1]).to_pydatetime()
        return Quote(
            symbol=canonical,
            market_id=self.market_id,
            last=last_px,
            open=float(last["open"]),
            high=float(last["high"]),
            low=float(last["low"]),
            prev_close=prev_close,
            volume=float(last["volume"]),
            change=change,
            change_pct=change_pct,
            timestamp=ts,
            delayed=True,
        )

    def instrument(self, symbol: str) -> Instrument:
        canonical = self.normalize_symbol(symbol)
        lot = self.lot_size(canonical)
        return Instrument(
            symbol=canonical,
            market_id=self.market_id,
            name=self.universe().get(canonical, canonical),
            currency=self.profile.currency,
            lot_size=lot if lot > 0 else 1,
            timezone=self.timezone,
            session_hours=self.session_hours,
        )

    def search(self, query: str) -> list[Instrument]:
        q = query.strip().upper()
        if not q:
            return [self.instrument(sym) for sym in list(self.universe())[:20]]
        hits: list[Instrument] = []
        seen: set[str] = set()
        for sym, name in self.universe().items():
            if q in sym.upper() or q in name.upper():
                hits.append(self.instrument(sym))
                seen.add(sym)
        canonical = self.normalize_symbol(q)
        if canonical not in seen:
            hits.insert(0, self.instrument(canonical))
        return hits[:20]
