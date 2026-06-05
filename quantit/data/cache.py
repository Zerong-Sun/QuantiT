"""Local Parquet cache for market data."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from quantit.utils.config import get_config


class DataCache:
    """Parquet-based local cache for OHLCV data."""

    def __init__(self, cache_dir: Path | None = None) -> None:
        self.cache_dir = cache_dir or get_config().cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, symbol: str, interval: str) -> Path:
        safe_symbol = symbol.replace("/", "_").upper()
        return self.cache_dir / f"{safe_symbol}_{interval}.parquet"

    def get(self, symbol: str, interval: str = "1d") -> pd.DataFrame | None:
        """Load cached data if available."""
        path = self._path(symbol, interval)
        if not path.exists():
            return None
        return pd.read_parquet(path)

    def set(self, symbol: str, df: pd.DataFrame, interval: str = "1d") -> None:
        """Save data to cache."""
        path = self._path(symbol, interval)
        df.to_parquet(path)

    def has(self, symbol: str, interval: str = "1d") -> bool:
        """Check if cache exists."""
        return self._path(symbol, interval).exists()
