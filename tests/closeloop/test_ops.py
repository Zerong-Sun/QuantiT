"""Operator lookahead and shape tests."""

from __future__ import annotations

import numpy as np
import pandas as pd

from closeloop.factors.ops import delay, rank, ts_sum, UnsupportedOperatorError, indneutralize


def _col() -> pd.DataFrame:
    return pd.DataFrame({"a": [1.0, 2.0, 3.0, 10.0], "b": [4.0, 3.0, 2.0, 1.0]})


def test_delay_is_past_only():
    frame = _col()
    out = delay(frame, 1)
    assert pd.isna(out.iloc[0, 0])
    assert out.iloc[1, 0] == 1.0
    assert out.iloc[3, 0] == 3.0


def test_ts_sum_does_not_use_future():
    frame = _col()
    out = ts_sum(frame, 2)
    assert pd.isna(out.iloc[0, 0])
    assert out.iloc[1, 0] == 3.0
    assert out.iloc[2, 0] == 5.0


def test_rank_is_cross_sectional():
    frame = pd.DataFrame({"a": [1.0, 10.0], "b": [3.0, 20.0], "c": [2.0, 30.0]})
    out = rank(frame)
    assert np.isclose(out.iloc[0]["a"], 1 / 3)
    assert np.isclose(out.iloc[0]["b"], 1.0)


def test_indneutralize_raises():
    try:
        indneutralize(_col())
    except UnsupportedOperatorError:
        return
    raise AssertionError("expected UnsupportedOperatorError")
