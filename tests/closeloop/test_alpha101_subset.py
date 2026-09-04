from __future__ import annotations

from closeloop.data.fixture import FixtureDataPlane
from closeloop.factors.alpha101 import (
    INDUSTRY_OR_CAP,
    compute_alpha,
    list_alphas,
    supported_ids,
)


def test_registry_has_101_entries():
    rows = list_alphas()
    assert len(rows) == 101
    assert {r["alpha_id"] for r in rows} == {f"{i:03d}" for i in range(1, 102)}
    needs_fund = {r["alpha_id"] for r in rows if r["requires_industry_or_cap"]}
    assert needs_fund == set(INDUSTRY_OR_CAP)
    assert all(r["supported"] for r in rows)


def test_alpha_001_006_012_shapes():
    panel = FixtureDataPlane(n_days=80, n_instruments=8).load_panel("2020-01-01", "2021-12-31")
    for aid in ("001", "006", "012"):
        out = compute_alpha(aid, panel)
        assert out.shape == panel["close"].shape
        assert list(out.columns) == list(panel["close"].columns)


def test_supported_ids_include_industry_formulas():
    assert "006" in supported_ids()
    assert "048" in supported_ids()
    assert len(supported_ids()) == 101


def test_all_supported_alphas_compute_on_fixture():
    panel = FixtureDataPlane(n_days=80, n_instruments=6, seed=2).load_panel("2020-01-01", "2021-12-31")
    expected = panel["close"].shape
    for aid in supported_ids():
        out = compute_alpha(aid, panel)
        assert out.shape == expected, aid
