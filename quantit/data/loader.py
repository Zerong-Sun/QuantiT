"""Data loader with caching support."""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from quantit.data.cache import DataCache
from quantit.data.provider import DataProvider, YahooFinanceProvider


class DataLoader:
    """Load market data with automatic caching."""

    def __init__(
        self,
        provider: DataProvider | None = None,
        cache: DataCache | None = None,
    ) -> None:
        self.provider = provider or YahooFinanceProvider()
        self.cache = cache or DataCache()

    @staticmethod
    def _covers(cached: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> bool:
        if cached is None or cached.empty:
            return False
        return cached.index.min() <= start and cached.index.max() >= end

    def _merge_cache(self, existing: pd.DataFrame | None, incoming: pd.DataFrame) -> pd.DataFrame:
        if existing is None or existing.empty:
            combined = incoming.sort_index()
        else:
            combined = pd.concat([existing, incoming])
            combined = combined[~combined.index.duplicated(keep="last")]
            combined = combined.sort_index()
        return combined

    def load(
        self,
        symbol: str,
        start: str | datetime,
        end: str | datetime,
        interval: str = "1d",
        use_cache: bool = True,
    ) -> pd.DataFrame:
        """Load OHLCV data, using cache when possible.

        Cache is used only when it fully covers ``[start, end]``. Otherwise the
        missing prefix and/or suffix is fetched and merged into the Parquet cache.
        """
        start_ts = pd.Timestamp(start)
        end_ts = pd.Timestamp(end)

        cached = self.cache.get(symbol, interval) if use_cache else None

        if use_cache and self._covers(cached, start_ts, end_ts):
            mask = (cached.index >= start_ts) & (cached.index <= end_ts)
            return cached.loc[mask].copy()

        frames: list[pd.DataFrame] = []
        if cached is None or cached.empty:
            frames.append(self.provider.fetch(symbol, start, end, interval))
        else:
            if cached.index.min() > start_ts:
                frames.append(self.provider.fetch(symbol, start, cached.index.min(), interval))
            if cached.index.max() < end_ts:
                frames.append(self.provider.fetch(symbol, cached.index.max(), end, interval))
            if not frames:
                frames.append(self.provider.fetch(symbol, start, end, interval))

        fetched = pd.concat(frames) if len(frames) > 1 else frames[0]
        fetched = fetched.sort_index()

        if use_cache:
            combined = self._merge_cache(cached, fetched)
            self.cache.set(symbol, combined, interval)
            mask = (combined.index >= start_ts) & (combined.index <= end_ts)
            return combined.loc[mask].copy()

        mask = (fetched.index >= start_ts) & (fetched.index <= end_ts)
        return fetched.loc[mask].copy()

    def load_multi(
        self,
        symbols: list[str],
        start: str | datetime,
        end: str | datetime,
        interval: str = "1d",
        skip_missing: bool = False,
    ) -> dict[str, pd.DataFrame]:
        """Load data for multiple symbols.

        When ``skip_missing`` is true, symbols that fail to fetch are omitted
        instead of raising.
        """
        result: dict[str, pd.DataFrame] = {}
        for sym in symbols:
            try:
                result[sym] = self.load(sym, start, end, interval)
            except Exception:
                if skip_missing:
                    continue
                raise
        return result
