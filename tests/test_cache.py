"""Cache coverage tests (no network)."""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from quantit.data.cache import DataCache
from quantit.data.loader import DataLoader
from quantit.data.provider import DataProvider


def _ohlcv(start: str, end: str, price: float = 100.0) -> pd.DataFrame:
    idx = pd.date_range(start, end, freq="D")
    n = len(idx)
    return pd.DataFrame(
        {
            "open": [price] * n,
            "high": [price + 1] * n,
            "low": [price - 1] * n,
            "close": [price] * n,
            "volume": [1_000] * n,
        },
        index=idx,
    )


class RecordingProvider(DataProvider):
    def __init__(self) -> None:
        self.calls: list[tuple[str, pd.Timestamp, pd.Timestamp, str]] = []

    def fetch(
        self,
        symbol: str,
        start: str | datetime,
        end: str | datetime,
        interval: str = "1d",
    ) -> pd.DataFrame:
        start_ts = pd.Timestamp(start)
        end_ts = pd.Timestamp(end)
        self.calls.append((symbol, start_ts, end_ts, interval))
        return _ohlcv(start_ts, end_ts)


def test_cache_hit_when_fully_covered(tmp_path) -> None:
    cache = DataCache(cache_dir=tmp_path)
    cache.set("AAPL", _ohlcv("2020-01-01", "2020-01-31"))
    provider = RecordingProvider()
    loader = DataLoader(provider=provider, cache=cache)

    df = loader.load("AAPL", "2020-01-10", "2020-01-20")

    assert provider.calls == []
    assert df.index.min() == pd.Timestamp("2020-01-10")
    assert df.index.max() == pd.Timestamp("2020-01-20")


def test_cache_fetches_prefix_and_suffix_gaps(tmp_path) -> None:
    cache = DataCache(cache_dir=tmp_path)
    cache.set("AAPL", _ohlcv("2020-01-10", "2020-01-20"))
    provider = RecordingProvider()
    loader = DataLoader(provider=provider, cache=cache)

    df = loader.load("AAPL", "2020-01-01", "2020-01-31")

    assert len(provider.calls) == 2
    assert provider.calls[0][1] == pd.Timestamp("2020-01-01")
    assert provider.calls[0][2] == pd.Timestamp("2020-01-10")
    assert provider.calls[1][1] == pd.Timestamp("2020-01-20")
    assert provider.calls[1][2] == pd.Timestamp("2020-01-31")
    assert df.index.min() == pd.Timestamp("2020-01-01")
    assert df.index.max() == pd.Timestamp("2020-01-31")

    cached = cache.get("AAPL")
    assert cached is not None
    assert cached.index.min() == pd.Timestamp("2020-01-01")
    assert cached.index.max() == pd.Timestamp("2020-01-31")


def test_empty_cache_fetches_full_range(tmp_path) -> None:
    cache = DataCache(cache_dir=tmp_path)
    provider = RecordingProvider()
    loader = DataLoader(provider=provider, cache=cache)

    df = loader.load("MSFT", "2020-02-01", "2020-02-05")

    assert len(provider.calls) == 1
    assert list(df.index) == list(pd.date_range("2020-02-01", "2020-02-05", freq="D"))


def test_cache_hit_when_start_is_non_session(tmp_path) -> None:
    """Jan 1 is a holiday; cache starting Jan 2 still covers 2020-01-01."""
    cache = DataCache(cache_dir=tmp_path)
    cache.set("AAPL", _ohlcv("2020-01-02", "2020-01-31"))
    provider = RecordingProvider()
    loader = DataLoader(provider=provider, cache=cache)

    df = loader.load("AAPL", "2020-01-01", "2020-01-31")

    assert provider.calls == []
    assert df.index.min() == pd.Timestamp("2020-01-02")
    assert df.index.max() == pd.Timestamp("2020-01-31")
