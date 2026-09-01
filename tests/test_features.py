"""Feature numerical checks against pandas."""

from __future__ import annotations

import numpy as np
import pandas as pd

from quantit.features.technical import RSIFeature, SMAFeature


def _ohlcv(n: int = 50) -> pd.DataFrame:
    dates = pd.date_range("2020-01-01", periods=n, freq="B")
    close = pd.Series(np.linspace(100, 120, n), index=dates)
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": 1_000,
        }
    )


def test_sma_matches_rolling_mean() -> None:
    df = _ohlcv()
    period = 10
    actual = SMAFeature(period=period).compute(df)
    expected = df["close"].rolling(period).mean()
    pd.testing.assert_series_equal(actual, expected, check_names=False)


def test_rsi_matches_ewm_formula() -> None:
    df = _ohlcv()
    period = 14
    actual = RSIFeature(period=period).compute(df)

    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(span=period, adjust=False).mean()
    avg_loss = loss.ewm(span=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    expected = 100 - (100 / (1 + rs))

    pd.testing.assert_series_equal(actual, expected, check_names=False)
