"""IC / quantile / turnover gates. Thresholds are explicit, not tear-sheet HTML."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from closeloop.validate.adapter import CleanFactor


@dataclass(frozen=True)
class GateThresholds:
    ic_mean_abs: float = 0.02
    ic_ir: float = 0.5
    require_quantile_spread_positive: bool = True
    period: int = 1


@dataclass
class GateReport:
    passed: bool
    ic_mean: float
    ic_ir: float
    quantile_spread: float
    turnover: float
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "ic_mean": self.ic_mean,
            "ic_ir": self.ic_ir,
            "quantile_spread": self.quantile_spread,
            "turnover": self.turnover,
            "reasons": list(self.reasons),
        }


def _ic_series(clean: CleanFactor, period: int) -> pd.Series:
    if period not in clean.data.columns:
        period = clean.periods[0]
    frame = clean.data[["factor", period]].dropna()

    def _corr(g: pd.DataFrame) -> float:
        if len(g) < 3:
            return float("nan")
        return float(g["factor"].corr(g[period]))

    return frame.groupby(level="date").apply(_corr)


def _quantile_spread(clean: CleanFactor, period: int) -> float:
    if "factor_quantile" not in clean.data.columns or period not in clean.data.columns:
        return float("nan")
    frame = clean.data[["factor_quantile", period]].dropna()
    if frame.empty:
        return float("nan")
    means = frame.groupby("factor_quantile")[period].mean()
    if means.empty:
        return float("nan")
    return float(means.loc[means.index.max()] - means.loc[means.index.min()])


def _turnover(clean: CleanFactor) -> float:
    q = clean.data["factor_quantile"].unstack("asset")
    if q.shape[0] < 2:
        return float("nan")
    changed = q.ne(q.shift(1))
    valid = q.notna() & q.shift(1).notna()
    denom = valid.sum(axis=1).replace(0, pd.NA)
    return float((changed & valid).sum(axis=1).div(denom).mean())


def evaluate(clean: CleanFactor, thresholds: GateThresholds | None = None) -> GateReport:
    th = thresholds or GateThresholds()
    ic = _ic_series(clean, th.period).dropna()
    ic_mean = float(ic.mean()) if len(ic) else float("nan")
    ic_std = float(ic.std(ddof=1)) if len(ic) > 1 else float("nan")
    ic_ir = float(ic_mean / ic_std) if ic_std and ic_std == ic_std and ic_std != 0 else float("nan")
    spread = _quantile_spread(clean, th.period)
    turnover = _turnover(clean)

    reasons: list[str] = []
    passed = True
    if not (abs(ic_mean) >= th.ic_mean_abs):
        passed = False
        reasons.append(f"|IC mean| {ic_mean:.4f} < {th.ic_mean_abs}")
    if not (abs(ic_ir) >= th.ic_ir if ic_ir == ic_ir else False):
        passed = False
        reasons.append(f"|IC_IR| {ic_ir:.4f} < {th.ic_ir}")
    if th.require_quantile_spread_positive and not (spread == spread and spread > 0):
        passed = False
        reasons.append(f"Qmax-Qmin spread {spread:.4f} is not positive")
    if passed:
        reasons.append("all gates passed")
    return GateReport(
        passed=passed,
        ic_mean=ic_mean,
        ic_ir=ic_ir,
        quantile_spread=spread,
        turnover=turnover,
        reasons=reasons,
    )
