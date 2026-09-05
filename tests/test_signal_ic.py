"""Alphalens-style IC on a basket TSMOM signal (synthetic, no network)."""

from __future__ import annotations

import pandas as pd
import pytest

from quantit.research.signal_ic import diagnose_basket_tsmom, spearman_ic
from quantit.strategy.hk_book import equal_weight_index


def _ohlcv(prices: list[float], start: str = "2018-01-01") -> pd.DataFrame:
    dates = pd.date_range(start, periods=len(prices), freq="B")
    return pd.DataFrame(
        {
            "open": prices,
            "high": [p + 0.5 for p in prices],
            "low": [max(0.1, p - 0.5) for p in prices],
            "close": prices,
            "volume": [1_000_000.0] * len(prices),
        },
        index=dates,
    )


def test_spearman_ic_is_one_when_ranks_match() -> None:
    signal = pd.Series([1.0, 2.0, 3.0, 4.0])
    fwd = pd.Series([0.1, 0.2, 0.3, 0.4])
    assert spearman_ic(signal, fwd) == pytest.approx(1.0)


def test_diagnose_finds_positive_ic_on_trending_book() -> None:
    n = 400
    a = [100.0 + i * 0.4 for i in range(n)]
    b = [80.0 + i * 0.35 for i in range(n)]
    book = {"0002.HK": _ohlcv(a), "0005.HK": _ohlcv(b)}
    report = diagnose_basket_tsmom(book, lookback=60, skip=5, horizon=1)
    assert report["n"] > 200
    assert report["ic"] > 0
    idx = equal_weight_index(book)
    assert idx.iloc[-1] > idx.iloc[0]


def test_diagnose_splits_on_vs_off_day_returns() -> None:
    n = 400
    prices = [100.0]
    for i in range(1, n):
        prices.append(prices[-1] * (1.02 if i % 40 < 30 else 0.97))
    book = {"AAA": _ohlcv(prices), "BBB": _ohlcv([p * 0.9 for p in prices])}
    report = diagnose_basket_tsmom(book, lookback=20, skip=0, horizon=1)
    assert "on_mean" in report and "off_mean" in report
    assert report["on_share"] > 0
    assert report["off_share"] > 0


def test_diagnose_empty_and_bad_skip_return_zero_n() -> None:
    empty = diagnose_basket_tsmom({}, lookback=20, skip=0)
    assert empty["n"] == 0
    assert "on_share" in empty
    book = {"AAA": _ohlcv([100.0 + i for i in range(50)])}
    bad = diagnose_basket_tsmom(book, lookback=10, skip=10)
    assert bad["n"] == 0


def test_spearman_constant_signal_is_nan() -> None:
    value = spearman_ic(pd.Series([1.0, 1.0, 1.0, 1.0]), pd.Series([0.1, 0.2, 0.3, 0.4]))
    assert value != value


def test_diagnose_cached_rejects_unknown_market() -> None:
    from quantit.research.signal_ic import diagnose_cached_quality

    with pytest.raises(ValueError, match="unknown quality market"):
        diagnose_cached_quality("jp")


def test_diagnose_cached_reads_live_skip(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from quantit.research.params import write_active_params
    from quantit.research.signal_ic import diagnose_cached_quality

    write_active_params(
        {"strategies": {"cn_quality_book": {"lookback": 252, "skip": 0}}}
    )
    from quantit.data.cache import DataCache
    from quantit.research.universes import CN_QUALITY

    cache = DataCache(tmp_path)
    n = 40
    for symbol in CN_QUALITY:
        cache.set(symbol, _ohlcv([100.0 + i * 0.2 for i in range(n)], start="2020-01-01"))
    report = diagnose_cached_quality(
        "cn", start="2020-01-01", end="2020-12-31", cache=cache
    )
    assert report["skip"] == 0
    assert report["lookback"] == 252


def test_cached_quality_ic_runs_when_bars_exist() -> None:
    from quantit.research.signal_ic import diagnose_cached_quality, load_cached_book
    from quantit.research.universes import HK_QUALITY

    book = load_cached_book(HK_QUALITY, "2012-01-01", "2024-12-31")
    if len(book) < 2:
        pytest.skip("no cached HK quality bars")
    report = diagnose_cached_quality("hk")
    assert report["n"] > 100
    assert "ic" in report
    assert "on_mean" in report
