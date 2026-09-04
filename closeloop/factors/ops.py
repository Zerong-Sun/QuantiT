"""WorldQuant-style operators on dates × instruments DataFrames.

Windows only look backward (including t). ``delay(x, d)`` is ``x.shift(d)``.
``indneutralize`` is intentionally unimplemented in v1.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


class UnsupportedOperatorError(RuntimeError):
    pass


def _win(d: float | int) -> int:
    return max(1, int(round(float(d))))


def _align(x: pd.DataFrame, y: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    idx = x.index.intersection(y.index)
    cols = x.columns.intersection(y.columns)
    return x.loc[idx, cols], y.loc[idx, cols]


def rank(x: pd.DataFrame) -> pd.DataFrame:
    return x.rank(axis=1, pct=True)


def delay(x: pd.DataFrame, d: float | int) -> pd.DataFrame:
    return x.shift(_win(d))


def delta(x: pd.DataFrame, d: float | int) -> pd.DataFrame:
    return x.diff(_win(d))


def ts_sum(x: pd.DataFrame, d: float | int) -> pd.DataFrame:
    w = _win(d)
    return x.rolling(w, min_periods=w).sum()


def ts_mean(x: pd.DataFrame, d: float | int) -> pd.DataFrame:
    w = _win(d)
    return x.rolling(w, min_periods=w).mean()


def ts_min(x: pd.DataFrame, d: float | int) -> pd.DataFrame:
    w = _win(d)
    return x.rolling(w, min_periods=w).min()


def ts_max(x: pd.DataFrame, d: float | int) -> pd.DataFrame:
    w = _win(d)
    return x.rolling(w, min_periods=w).max()


def ts_std(x: pd.DataFrame, d: float | int) -> pd.DataFrame:
    w = _win(d)
    return x.rolling(w, min_periods=w).std()


def stddev(x: pd.DataFrame, d: float | int) -> pd.DataFrame:
    return ts_std(x, d)


def ts_product(x: pd.DataFrame, d: float | int) -> pd.DataFrame:
    w = _win(d)
    return x.rolling(w, min_periods=w).apply(np.prod, raw=True)


def ts_argmax(x: pd.DataFrame, d: float | int) -> pd.DataFrame:
    w = _win(d)
    return x.rolling(w, min_periods=w).apply(lambda a: float(np.argmax(a)), raw=True)


def ts_argmin(x: pd.DataFrame, d: float | int) -> pd.DataFrame:
    w = _win(d)
    return x.rolling(w, min_periods=w).apply(lambda a: float(np.argmin(a)), raw=True)


def ts_rank(x: pd.DataFrame, d: float | int) -> pd.DataFrame:
    w = _win(d)

    def _rank(a: np.ndarray) -> float:
        last = a[-1]
        return float((a <= last).sum()) / float(len(a))

    return x.rolling(w, min_periods=w).apply(_rank, raw=True)


def decay_linear(x: pd.DataFrame, d: float | int) -> pd.DataFrame:
    w = _win(d)
    weights = np.arange(1, w + 1, dtype=float)
    denom = weights.sum()

    def _decay(a: np.ndarray) -> float:
        return float(np.dot(a, weights) / denom)

    return x.rolling(w, min_periods=w).apply(_decay, raw=True)


def correlation(x: pd.DataFrame, y: pd.DataFrame, d: float | int) -> pd.DataFrame:
    a, b = _align(x, y)
    w = _win(d)
    return a.rolling(w, min_periods=w).corr(b)


def covariance(x: pd.DataFrame, y: pd.DataFrame, d: float | int) -> pd.DataFrame:
    a, b = _align(x, y)
    w = _win(d)
    return a.rolling(w, min_periods=w).cov(b)


def scale(x: pd.DataFrame, a: float = 1.0) -> pd.DataFrame:
    denom = x.abs().sum(axis=1).replace(0.0, np.nan)
    return x.mul(float(a)).div(denom, axis=0)


def signedpower(x: pd.DataFrame, a) -> pd.DataFrame:
    if isinstance(a, pd.DataFrame):
        a, x = _align(a, x)
        return np.sign(x) * np.abs(x).pow(a)
    return np.sign(x) * np.abs(x).pow(float(a))


def sign(x: pd.DataFrame) -> pd.DataFrame:
    return np.sign(x)


def log(x: pd.DataFrame) -> pd.DataFrame:
    return np.log(x.where(x > 0))


def abs_(x: pd.DataFrame) -> pd.DataFrame:
    return x.abs()


def ternary(cond: pd.DataFrame, left, right) -> pd.DataFrame:
    """Element-wise ``left if cond else right`` (cond is boolean)."""
    if not isinstance(left, pd.DataFrame):
        left = pd.DataFrame(left, index=cond.index, columns=cond.columns, dtype=float)
    if not isinstance(right, pd.DataFrame):
        right = pd.DataFrame(right, index=cond.index, columns=cond.columns, dtype=float)
    left, _ = _align(left, cond)
    right, cond = _align(right, cond)
    left, cond = _align(left, cond)
    return left.where(cond.astype(bool), right)


def maximum(x: pd.DataFrame, y: pd.DataFrame) -> pd.DataFrame:
    a, b = _align(x, y)
    return np.maximum(a, b)


def minimum(x: pd.DataFrame, y: pd.DataFrame) -> pd.DataFrame:
    a, b = _align(x, y)
    return np.minimum(a, b)


def adv(volume: pd.DataFrame, d: float | int) -> pd.DataFrame:
    return ts_mean(volume, d)


def indneutralize(x: pd.DataFrame, industry: pd.DataFrame | None = None, *args, **kwargs) -> pd.DataFrame:
    """Subtract industry-group mean on each date. ``industry`` is dates×instruments ids."""
    if industry is None:
        raise UnsupportedOperatorError(
            "indneutralize requires an industry map; pass Fields.industry"
        )
    a, g = _align(x, industry)
    try:
        long = a.stack(future_stack=True)
        grp = g.stack(future_stack=True).reindex(long.index)
    except TypeError:
        long = a.stack(dropna=False)
        grp = g.stack(dropna=False).reindex(long.index)
    dates = long.index.get_level_values(0)
    mu = long.groupby([dates, grp], dropna=False).transform("mean")
    return (long - mu).unstack()


def factor_stack(frame: pd.DataFrame) -> pd.Series:
    """dates×instruments → MultiIndex (date, asset) Series."""
    try:
        stacked = frame.stack(future_stack=True)
    except TypeError:
        stacked = frame.stack(dropna=False)
    stacked.index.names = ["date", "asset"]
    return stacked
