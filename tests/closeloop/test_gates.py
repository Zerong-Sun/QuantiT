from __future__ import annotations

import numpy as np
import pandas as pd

from closeloop.validate.adapter import get_clean_factor_and_forward_returns
from closeloop.validate.gates import GateThresholds, evaluate


def _dates(n: int = 40) -> pd.DatetimeIndex:
    return pd.bdate_range("2020-01-02", periods=n)


def _monotonic_case():
    dates = _dates(50)
    assets = ["SH600000", "SH600001", "SZ000001", "SZ000002"]
    rng = np.random.default_rng(0)
    prices = pd.DataFrame(100.0, index=dates, columns=assets)
    for i, a in enumerate(assets):
        prices[a] = 100 + i * 5 + np.cumsum(rng.normal(0.05 * (i + 1), 0.2, size=len(dates)))
    fwd = prices.shift(-1) / prices - 1
    factor = fwd.copy()
    return factor, prices


def _noise_case():
    dates = _dates(50)
    assets = ["SH600000", "SH600001", "SZ000001", "SZ000002"]
    rng = np.random.default_rng(1)
    prices = pd.DataFrame(rng.uniform(90, 110, size=(len(dates), 4)), index=dates, columns=assets)
    factor = pd.DataFrame(rng.normal(size=prices.shape), index=dates, columns=assets)
    return factor, prices


def test_monotonic_factor_passes_gates():
    factor, prices = _monotonic_case()
    clean = get_clean_factor_and_forward_returns(factor, prices, periods=(1, 5, 10), quantiles=4)
    report = evaluate(clean, GateThresholds(ic_mean_abs=0.02, ic_ir=0.5, period=1))
    assert report.passed, report.reasons
    assert report.ic_mean > 0.02
    assert report.quantile_spread > 0


def test_noise_factor_fails_gates():
    factor, prices = _noise_case()
    clean = get_clean_factor_and_forward_returns(factor, prices, periods=(1, 5), quantiles=4)
    report = evaluate(clean, GateThresholds(ic_mean_abs=0.05, ic_ir=0.8, period=1))
    assert report.passed is False
    assert report.reasons
