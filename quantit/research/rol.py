"""Risk Overlay Layer gates (ROL v0.1.1).

Not attached to ``--promote`` / ``maybe_promote``. Does not write
``active_params.yaml``. Does not loosen report/promote or Closeloop IC/IR
gates. Thresholds here are a frozen v0.1.1 sketch; a mathematician will
calibrate numerics.

Inputs are explicit kwargs so tests can inject synthetic series without a
full backtest.

P-rules
-------
P1: Required YAML keys; missing keys print/return a 补全向量. Twisting
    lookback / skip / τ / ρ / vol_lookback / strong_mom / invested_* (and
    unnamed knobs by default) cannot rescue a FAIL.
P2: Labels use a lag-1 **trading-day** calendar (holidays/suspensions are
    not sessions). Gross exposure ``G = Σ|w|``. G-cap applies only on
    lag-1-active days.
P3: ``n = |target quality universe|`` is fixed. A shrinking held set must
    not raise the per-name cap (``1/n``).
P4: Overlay metric must satisfy median ≤ 1.5× baseline median **and**
    P95 ≤ 2.5× baseline P95 (or absolute 0.10). Median alone is not enough.
P5: Eligible days < 40 ⇒ ``rol_evidence=incomplete``, which invalidates
    the whole study evidence pack (no day-subset bypass). ≥40 with a band
    breach ⇒ FAIL.
P6: Unlabeled derivative notionals > ε ⇒ FAIL.

R1: Paper halt 0.20 is not interchangeable with report max_dd −0.25.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from quantit.research.gates import GateResult

ROL_SPEC = "v0.1.1"

# Frozen; not the report-gate max_drawdown default (−0.25).
PAPER_HALT = 0.20
REPORT_MAX_DRAWDOWN = -0.25

REQUIRED_YAML_KEYS: tuple[str, ...] = (
    "lookback",
    "skip",
    "target_vol",  # τ
    "rho",  # ρ
    "vol_lookback",
    "strong_mom",
    "invested_on",
    "invested_strong",
)

P3_WEIGHT_CAP_NUMERATOR = 1.0
P4_MEDIAN_MULT = 1.5
P4_P95_MULT = 2.5
P4_P95_ABS = 0.10
P5_MIN_ELIGIBLE_DAYS = 40
P6_EPS = 1e-12
GROSS_EXPOSURE_CAP = 1.0

# Research knobs that must not flip a FAIL to PASS (R1).
_RESCUE_KNOBS = frozenset(
    {
        "lookback",
        "skip",
        "target_vol",
        "tau",
        "rho",
        "vol_lookback",
        "strong_mom",
        "invested_on",
        "invested_strong",
        "invested_off",
        "risk_off_scale",
        "max_leverage",
        "extra_unnamed_knob",
    }
)


def p3_weight_cap(n_target: int) -> float:
    """Per-name |w| cap from the *target* quality universe size."""
    n = int(n_target)
    if n <= 0:
        return 0.0
    return P3_WEIGHT_CAP_NUMERATOR / float(n)


def completion_vector(params: Mapping[str, Any] | None) -> tuple[str, ...]:
    """P1 补全向量: required YAML keys that are absent."""
    have = {str(k) for k in (params or {})}
    if "tau" in have:
        have.add("target_vol")
    return tuple(key for key in REQUIRED_YAML_KEYS if key not in have)


def _norm_ts(value: Any) -> pd.Timestamp:
    return pd.Timestamp(value).normalize()


def lag1_trading_labels(
    labels: Mapping[Any, Any] | pd.Series | Sequence[Any] | None,
    trading_days: Sequence[Any] | pd.DatetimeIndex | None,
    holidays: Sequence[Any] | None = None,
    suspensions: Sequence[Any] | None = None,
) -> pd.Series:
    """Shift labels by one *trading* session. Holidays/suspensions are dropped."""
    if trading_days is None:
        if labels is None:
            return pd.Series(dtype=float)
        series = pd.Series(labels)
        series.index = pd.DatetimeIndex([_norm_ts(i) for i in series.index])
        return series.shift(1)

    hol = {_norm_ts(d) for d in (holidays or [])}
    sus = {_norm_ts(d) for d in (suspensions or [])}
    blocked = hol | sus
    days = pd.DatetimeIndex([_norm_ts(d) for d in trading_days])
    days = days[~days.isin(list(blocked))]
    if labels is None:
        aligned = pd.Series(1.0, index=days)
        return aligned.shift(1)
    if isinstance(labels, (list, tuple)) and not isinstance(labels, (str, bytes)):
        raw = pd.Series(list(labels), index=pd.DatetimeIndex([_norm_ts(d) for d in trading_days]))
    else:
        raw = pd.Series(labels)
        raw.index = pd.DatetimeIndex([_norm_ts(i) for i in raw.index])
    aligned = raw.reindex(days)
    return aligned.shift(1)


def _gross_rows(
    weights: Mapping[str, float] | pd.DataFrame | None,
) -> list[tuple[pd.Timestamp | None, float, dict[str, float]]]:
    if weights is None:
        return []
    if isinstance(weights, pd.DataFrame):
        rows: list[tuple[pd.Timestamp | None, float, dict[str, float]]] = []
        for idx, row in weights.iterrows():
            numeric = {str(k): float(v) for k, v in row.items() if pd.notna(v)}
            g = float(sum(abs(v) for v in numeric.values()))
            rows.append((_norm_ts(idx), g, numeric))
        return rows
    numeric = {str(k): float(v) for k, v in dict(weights).items()}
    g = float(sum(abs(v) for v in numeric.values()))
    return [(None, g, numeric)]


def _as_float_list(values: Sequence[Any] | pd.Series | None) -> list[float] | None:
    if values is None:
        return None
    return [float(v) for v in list(values)]


def _as_bool_list(values: Sequence[Any] | pd.Series | None) -> list[bool] | None:
    if values is None:
        return None
    return [bool(v) for v in list(values)]


def _truthy(value: Any) -> bool:
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return False
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    return bool(value)


def evaluate_rol_gates(
    *,
    yaml_params: Mapping[str, Any] | None = None,
    weights: Mapping[str, float] | pd.DataFrame | None = None,
    labels: Mapping[Any, Any] | pd.Series | Sequence[Any] | None = None,
    trading_days: Sequence[Any] | pd.DatetimeIndex | None = None,
    holidays: Sequence[Any] | None = None,
    suspensions: Sequence[Any] | None = None,
    target_universe: Sequence[str] | None = None,
    held_universe: Sequence[str] | None = None,
    n_target: int | None = None,
    metric_series: Sequence[float] | pd.Series | None = None,
    baseline_series: Sequence[float] | pd.Series | None = None,
    eligible_mask: Sequence[bool] | pd.Series | None = None,
    band: tuple[float, float] | None = None,
    declared_eligible_days: int | None = None,
    unlabeled_derivative_notional: float = 0.0,
    labeled_derivative_notional: float = 0.0,
    cl_has_fills: bool = False,
    yaml_paths: Mapping[str, str | Path] | None = None,
    attempt_write_yaml: bool = False,
    max_drawdown: float | None = None,
    paper_halt: float | None = None,
    halt_threshold: float | None = None,
    **unused_knobs: Any,
) -> GateResult:
    """Risk Overlay Layer gates (ROL v0.1.1). Not attached to --promote.

    ``unused_knobs`` (lookback, skip, τ/rho, vol_lookback, invested_*, …) are
    accepted and ignored so twisting them cannot rescue a FAIL.
    """
    del labeled_derivative_notional  # labeled notionals are allowed; only unlabeled trip P6
    del held_universe  # never used to raise P3 caps
    del unused_knobs  # R1: unnamed knobs cannot rescue a FAIL
    del cl_has_fills
    del yaml_paths
    del attempt_write_yaml  # isolation: never write US/HK/CN YAML

    reasons: list[str] = []

    # --- P1 YAML completeness -------------------------------------------------
    if yaml_params is not None:
        missing = completion_vector(yaml_params)
        if missing:
            line = "P1 completion vector: " + ", ".join(missing)
            print(line)
            reasons.append(line)
            reasons.append("missing yaml keys: " + ", ".join(missing))

    # --- R1 paper halt ≠ report max_dd ---------------------------------------
    requested_halt = PAPER_HALT
    for raw in (paper_halt, halt_threshold):
        if raw is None:
            continue
        requested_halt = float(raw)
        if abs(requested_halt - PAPER_HALT) > 1e-12:
            reasons.append(
                f"paper halt {PAPER_HALT:.2f} is not interchangeable with "
                f"report max_dd {REPORT_MAX_DRAWDOWN}"
            )
            break
    halt = PAPER_HALT
    if max_drawdown is not None:
        dd = abs(float(max_drawdown))
        if dd > halt + 1e-12:
            reasons.append(
                f"P-halt: |max_drawdown| {dd:.2f} exceeds paper halt {halt:.2f} "
                f"(not report max_dd {REPORT_MAX_DRAWDOWN})"
            )

    # --- P2 lag-1 labels + G = Σ|w| ------------------------------------------
    lagged = None
    if labels is not None or trading_days is not None:
        lagged = lag1_trading_labels(labels, trading_days, holidays, suspensions)
    holiday_block = {_norm_ts(d) for d in (holidays or [])} | {
        _norm_ts(d) for d in (suspensions or [])
    }
    for day, gross, _w in _gross_rows(weights):
        active = True
        if lagged is not None and day is not None:
            if day in holiday_block:
                continue
            if day in lagged.index:
                active = _truthy(lagged.loc[day])
            else:
                active = False
        elif lagged is not None and day is None:
            # Snapshot weights: G-cap only if a lag-1 label is active.
            active = bool(lagged.dropna().map(_truthy).any()) if len(lagged) else False
        if active and gross > GROSS_EXPOSURE_CAP + 1e-12:
            reasons.append(
                f"P2 lag-1 gross exposure G=Σ|w| {gross:.4f} exceeds cap {GROSS_EXPOSURE_CAP:.2f}"
            )
            break

    # --- P3 concentration; n is |target quality universe| --------------------
    if weights is not None:
        n = n_target
        if n is None and target_universe is not None:
            n = len(list(target_universe))
        if n is None:
            reasons.append("P3 n=|target quality universe| is required (cannot infer from holdings)")
        else:
            cap = p3_weight_cap(int(n))
            for day, _g, wmap in _gross_rows(weights):
                if day is not None and day in holiday_block:
                    continue
                peak = max((abs(v) for v in wmap.values()), default=0.0)
                if peak > cap + 1e-12:
                    reasons.append(
                        f"P3 |w| {peak:.4f} exceeds cap {cap:.4f} "
                        f"(n={int(n)} target universe, not holdings)"
                    )
                    break

    # --- P4 median×1.5 and P95×2.5 (or abs 0.10) -----------------------------
    metric = _as_float_list(metric_series)
    baseline = _as_float_list(baseline_series)
    if metric is not None and baseline is not None and metric and baseline:
        med = float(np.median(metric))
        base_med = float(np.median(baseline))
        p95 = float(np.quantile(metric, 0.95))
        base_p95 = float(np.quantile(baseline, 0.95))
        median_ok = med <= P4_MEDIAN_MULT * base_med + 1e-12
        p95_ok = p95 <= P4_P95_MULT * base_p95 + 1e-12 or p95 <= P4_P95_ABS + 1e-12
        if not median_ok or not p95_ok:
            reasons.append(
                f"P4 median {med:.4f} vs {P4_MEDIAN_MULT}×{base_med:.4f}; "
                f"P95 {p95:.4f} exceeds {P4_P95_MULT}× baseline P95 {base_p95:.4f} "
                f"(or absolute {P4_P95_ABS:.2f})"
            )

    # --- P5 eligible-day evidence --------------------------------------------
    mask = _as_bool_list(eligible_mask)
    if mask is not None:
        n_eligible = int(sum(mask))
        if declared_eligible_days is not None and int(declared_eligible_days) != n_eligible:
            # Subset of a longer pack is not a bypass.
            n_eligible = min(n_eligible, int(declared_eligible_days))
            if int(declared_eligible_days) >= P5_MIN_ELIGIBLE_DAYS and n_eligible < P5_MIN_ELIGIBLE_DAYS:
                n_eligible = min(n_eligible, P5_MIN_ELIGIBLE_DAYS - 1)
        if n_eligible < P5_MIN_ELIGIBLE_DAYS:
            reasons.append(
                "P5 rol_evidence=incomplete; incomplete invalidates the whole "
                "study evidence pack"
            )
        elif band is not None and metric is not None:
            lo, hi = float(band[0]), float(band[1])
            paired = list(zip(mask, metric))
            if any(flag and (val < lo - 1e-12 or val > hi + 1e-12) for flag, val in paired):
                reasons.append(f"P5 band breach outside [{lo:.4f}, {hi:.4f}]")
        elif band is not None:
            lo, hi = float(band[0]), float(band[1])
            reasons.append(f"P5 band [{lo:.4f}, {hi:.4f}] requires metric_series")

    # --- P6 unlabeled derivatives --------------------------------------------
    if float(unlabeled_derivative_notional) > P6_EPS:
        reasons.append(
            f"P6 unlabeled derivative notional {float(unlabeled_derivative_notional):.3g} > ε={P6_EPS:g}"
        )

    return GateResult(passed=not reasons, reasons=tuple(reasons))
