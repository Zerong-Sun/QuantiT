"""Cross-sectional winsorize and z-score. No lookahead (row-wise on date)."""

from __future__ import annotations

import numpy as np
import pandas as pd


def cs_winsorize(x: pd.DataFrame, limits: tuple[float, float] = (0.01, 0.99)) -> pd.DataFrame:
    lo = x.quantile(limits[0], axis=1)
    hi = x.quantile(limits[1], axis=1)
    return x.clip(lower=lo, upper=hi, axis=0)


def cs_zscore(x: pd.DataFrame) -> pd.DataFrame:
    mu = x.mean(axis=1)
    sd = x.std(axis=1, ddof=0).replace(0.0, np.nan)
    return x.sub(mu, axis=0).div(sd, axis=0)


def prepare_factor(
    x: pd.DataFrame,
    *,
    winsorize: bool = True,
    zscore: bool = True,
    limits: tuple[float, float] = (0.01, 0.99),
) -> pd.DataFrame:
    out = x
    if winsorize:
        out = cs_winsorize(out, limits=limits)
    if zscore:
        out = cs_zscore(out)
    return out
