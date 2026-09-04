from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from closeloop.data.fixture import FixtureDataPlane
from closeloop.factors.alpha101 import INDUSTRY_OR_CAP, compute_alpha
from closeloop.factors.ops import indneutralize


def test_indneutralize_zero_group_mean():
    dates = pd.bdate_range("2020-01-02", periods=3)
    cols = ["A", "B", "C", "D"]
    x = pd.DataFrame([[1.0, 3.0, 10.0, 12.0]] * 3, index=dates, columns=cols)
    industry = pd.DataFrame([[0.0, 0.0, 1.0, 1.0]] * 3, index=dates, columns=cols)
    out = indneutralize(x, industry)
    # group 0: 1 and 3 → mean 2 → residuals -1, +1
    assert np.isclose(out.iloc[0]["A"], -1.0)
    assert np.isclose(out.iloc[0]["B"], 1.0)
    assert np.allclose(out.iloc[0, :2].mean(), 0.0)


def test_industry_alpha_raises_without_map():
    panel = FixtureDataPlane(n_days=40, n_instruments=6, with_fundamentals=False).load_panel(
        "2020-01-01", "2021-12-31"
    )
    with pytest.raises(Exception):
        compute_alpha("048", panel)


def test_industry_and_cap_alphas_compute_on_fixture():
    panel = FixtureDataPlane(n_days=80, n_instruments=8).load_panel("2020-01-01", "2021-12-31")
    assert "industry" in panel.columns.get_level_values("field")
    assert "cap" in panel.columns.get_level_values("field")
    for aid in ("048", "056", "058"):
        out = compute_alpha(aid, panel)
        assert out.shape == panel["close"].shape


def test_all_industry_alphas_listed():
    assert "048" in INDUSTRY_OR_CAP
    assert len(INDUSTRY_OR_CAP) == 19
