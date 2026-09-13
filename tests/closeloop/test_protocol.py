from __future__ import annotations

import warnings

import pandas as pd
import pytest

from closeloop.data.protocol import add_returns, field_frame, panel_from_fields


def _tiny_close_panel(close: pd.DataFrame) -> pd.DataFrame:
    return panel_from_fields(
        {
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume": close * 0.0 + 1_000.0,
            "vwap": close,
        }
    )


def test_add_returns_first_row_nan_and_no_future_warning():
    dates = pd.bdate_range("2020-01-02", periods=4)
    close = pd.DataFrame(
        {"SH600000": [10.0, 11.0, 12.1, 10.89], "SZ000001": [20.0, 20.0, 22.0, 19.8]},
        index=dates,
    )
    panel = _tiny_close_panel(close)

    with warnings.catch_warnings():
        warnings.simplefilter("error", FutureWarning)
        out = add_returns(panel)

    ret = field_frame(out, "returns")
    assert ret.iloc[0].isna().all()
    expected = close / close.shift(1) - 1.0
    pd.testing.assert_frame_equal(ret, expected, check_names=False, check_freq=False)


def test_add_returns_does_not_pad_internal_nan():
    dates = pd.bdate_range("2020-01-02", periods=4)
    close = pd.DataFrame({"SH600000": [10.0, 11.0, float("nan"), 12.0]}, index=dates)
    panel = _tiny_close_panel(close)

    with warnings.catch_warnings():
        warnings.simplefilter("error", FutureWarning)
        ret = field_frame(add_returns(panel), "returns")

    # fill_method='pad' would invent a 0.0 return on the NaN bar; we must not.
    assert pd.isna(ret.iloc[0, 0])
    assert ret.iloc[1, 0] == pytest.approx(0.1)
    assert pd.isna(ret.iloc[2, 0])
    assert pd.isna(ret.iloc[3, 0])


def test_add_returns_requests_fill_method_none(monkeypatch):
    """pandas 2.2 still defaults to pad and warns; pin the no-fill call."""
    seen: dict = {}
    original = pd.DataFrame.pct_change

    def wrapped(self, *args, **kwargs):
        seen["kwargs"] = dict(kwargs)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(pd.DataFrame, "pct_change", wrapped)
    dates = pd.bdate_range("2020-01-02", periods=3)
    close = pd.DataFrame({"SH600000": [10.0, 11.0, 12.1]}, index=dates)
    add_returns(_tiny_close_panel(close))
    assert seen.get("kwargs", {}).get("fill_method") is None
    assert "fill_method" in seen.get("kwargs", {})
