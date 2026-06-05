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

    def load(
        self,
        symbol: str,
        start: str | datetime,
        end: str | datetime,
        interval: str = "1d",
        use_cache: bool = True,
    ) -> pd.DataFrame:
        """Load OHLCV data, using cache when possible."""
        start_ts = pd.Timestamp(start)
        end_ts = pd.Timestamp(end)

        if use_cache:
            cached = self.cache.get(symbol, interval)
            if cached is not None:
                mask = (cached.index >= start_ts) & (cached.index <= end_ts)
                sliced = cached.loc[mask]
                if not sliced.empty:
                    return sliced.copy()

        df = self.provider.fetch(symbol, start, end, interval)
        df = df.sort_index()

        if use_cache:
            existing = self.cache.get(symbol, interval)
            if existing is not None:
                combined = pd.concat([existing, df])
                combined = combined[~combined.index.duplicated(keep="last")]
                combined = combined.sort_index()
                self.cache.set(symbol, combined, interval)
            else:
                self.cache.set(symbol, df, interval)

        mask = (df.index >= start_ts) & (df.index <= end_ts)
        return df.loc[mask].copy()

    def load_multi(
        self,
        symbols: list[str],
        start: str | datetime,
        end: str | datetime,
        interval: str = "1d",
    ) -> dict[str, pd.DataFrame]:
        """Load data for multiple symbols."""
        return {sym: self.load(sym, start, end, interval) for sym in symbols}
