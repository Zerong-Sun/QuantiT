"""Availability alignment, purged splits and cross-sectional evaluation."""
from __future__ import annotations

import numpy as np
import pandas as pd


def lag_features(features: pd.DataFrame, calendar: pd.DatetimeIndex, lag: int = 1) -> pd.DataFrame:
    """Shift by global market sessions, never by each stock's observed rows."""
    if lag < 1 or not isinstance(lag, int):
        raise ValueError("lag must be a positive integer")
    if features.index.has_duplicates or calendar.has_duplicates or not calendar.is_monotonic_increasing:
        raise ValueError("duplicate features or invalid calendar")
    wide = features.unstack("instrument").reindex(calendar).shift(lag)
    # Keep missing rows: do not shift across a stock suspension.
    return wide.stack("instrument", dropna=False).rename_axis(["date", "instrument"])


def forward_labels(close: pd.DataFrame, horizon: int) -> pd.Series:
    if not isinstance(horizon, int) or horizon < 1:
        raise ValueError("horizon must be a positive integer")
    label = close.shift(-horizon) / close - 1
    return label.stack(dropna=False).rename_axis(["date", "instrument"]).rename("label")


def training_dates(calendar: pd.DatetimeIndex, boundary: pd.Timestamp, horizon: int, embargo: int) -> pd.DatetimeIndex:
    """All labels end before boundary, plus embargo market sessions."""
    if horizon < 1 or embargo < 0:
        raise ValueError("invalid purge or embargo")
    cut = calendar.get_indexer([boundary])[0]
    if cut < 0:
        raise ValueError("boundary is outside calendar")
    return calendar[:max(0, cut - horizon - embargo)]


def daily_ic(prediction: pd.Series, label: pd.Series) -> dict:
    pairs = pd.concat([prediction.rename("prediction"), label.rename("label")], axis=1).dropna()
    values = []
    for _, group in pairs.groupby(level="date"):
        if len(group) >= 5 and group.prediction.nunique() > 1 and group.label.nunique() > 1:
            values.append(float(group.prediction.rank().corr(group.label.rank())))
    a = np.asarray(values)
    a = a[np.isfinite(a)]
    return {"rank_ic": float(a.mean()) if len(a) else None,
            "rank_ic_ir": float(a.mean() / a.std()) if len(a) > 1 and a.std() > 0 else None,
            "ic_sessions": len(a)}


def gate_reasons(metrics: dict, benchmark: dict, folds: list[dict], ic: dict) -> list[str]:
    """Frozen research gates. Passing these still does not authorize deployment."""
    reasons = []
    if metrics["sessions"] < 126:
        reasons.append("样本外交易日不足 126")
    if metrics.get("net_return") is None or metrics["net_return"] <= 0:
        reasons.append("样本外扣费收益未大于零")
    if metrics.get("net_return") is None or benchmark.get("net_return") is None or metrics["net_return"] <= benchmark["net_return"]:
        reasons.append("未跑赢同期等权对照")
    if metrics.get("max_drawdown") is None or metrics["max_drawdown"] < -0.20:
        reasons.append("最大回撤超过 20%")
    if metrics.get("sharpe") is None or metrics["sharpe"] < 0.5:
        reasons.append("年化夏普低于 0.5")
    if sum((f.get("net_return") or 0) > 0 for f in folds) < 2:
        reasons.append("三个滚动区间不足两个盈利")
    if ic.get("rank_ic") is None or ic["rank_ic"] <= 0:
        reasons.append("样本外日均 Rank IC 未大于零")
    if metrics.get("stale_valuation_sessions", 0):
        reasons.append("持仓估值存在缺失行情")
    return reasons
