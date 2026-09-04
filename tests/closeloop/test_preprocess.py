from __future__ import annotations

import numpy as np
import pandas as pd

from closeloop.factors.preprocess import cs_winsorize, cs_zscore, prepare_factor


def test_cs_zscore_row_mean_zero():
    frame = pd.DataFrame({"a": [1.0, 10.0], "b": [3.0, 20.0], "c": [2.0, 30.0]})
    z = cs_zscore(frame)
    assert np.allclose(z.mean(axis=1).to_numpy(), 0.0, atol=1e-10)


def test_winsorize_clips_tails():
    row = pd.DataFrame([[1.0, 2.0, 3.0, 4.0, 100.0]])
    clipped = cs_winsorize(row, limits=(0.2, 0.8))
    assert clipped.iloc[0].max() < 100.0


def test_prepare_factor_chains():
    frame = pd.DataFrame({"a": [1.0, 2.0], "b": [3.0, 100.0], "c": [2.0, 4.0]})
    out = prepare_factor(frame)
    assert out.shape == frame.shape
    assert np.isfinite(out.to_numpy()).any()
