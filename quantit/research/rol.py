"""Risk Overlay Layer gates (ROL v0.1.1 数值校准).

Not attached to ``--promote`` / ``maybe_promote``. Does not write
``active_params.yaml``. Does not loosen report/promote or Closeloop IC/IR
gates.

Inputs are explicit kwargs so tests can inject synthetic series without a
full backtest.

P-rules
-------
P1: ``completion_vector`` is YAML ∪ class defaults (full param vector).
    Missing YAML keys still FAIL; ``missing`` is a separate list.
    Live key ``risk_off_scale`` and ``rho`` are mutual aliases.
P2: Labels use a lag-1 **trading-day** calendar (holidays/suspensions are
    not sessions). ``G = Σ|w|``. Risk-on ``G≤I_strong``, risk-off ``G≤ρ``,
    read from YAML (else class defaults).
P3: ``n = |target quality universe|`` is fixed.
    ``p3_weight_cap = min(1/n + 0.05, 0.40)``.
P4: median ≤ 1.5× baseline median **and** P95 ≤ 2.5× baseline P95.
    Absolute median≤0.05 only if median(T̄)<0.01; P95≤0.10 only if
    P95(T̄)<0.02. No unconditional ``p95≤0.10`` escape.
P5: Eligible days < 40 ⇒ ``rol_evidence=incomplete``, which invalidates
    the whole study evidence pack (no day-subset bypass). ≥40 with a band
    breach ⇒ FAIL. Caller may pass ``band``; default ``[0.5, 1.5]`` (σ/τ).
P6: Unlabeled derivative notionals > ε ⇒ FAIL. ``ε=1e-12`` is an
    **absolute** notional cutoff, not a fraction of equity.

R1: Paper halt 0.20 is not interchangeable with report max_dd −0.25.
    Twisting lookback/skip/τ/ρ/vol_lookback/invested_* as extra kwargs
    cannot rescue a FAIL.
"""

from __future__ import annotations

import inspect
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from quantit.research.gates import GateResult

ROL_SPEC = "v0.1.1"

# Frozen; not the report-gate max_drawdown default (−0.25).
PAPER_HALT = 0.20
REPORT_MAX_DRAWDOWN = -0.25

# Live YAML uses risk_off_scale; rho is a mutual alias (P1).
REQUIRED_YAML_KEYS: tuple[str, ...] = (
    "lookback",
    "skip",
    "target_vol",  # τ
    "risk_off_scale",  # ρ
    "vol_lookback",
    "strong_mom",
    "invested_on",
    "invested_strong",  # I_strong
)

P3_WEIGHT_CAP_NUMERATOR = 1.0
P3_WEIGHT_CAP_ADD = 0.05
P3_WEIGHT_CAP_ABS_MAX = 0.40
P4_MEDIAN_MULT = 1.5
P4_P95_MULT = 2.5
P4_MEDIAN_ABS = 0.05
P4_P95_ABS = 0.10
P4_MEDIAN_ABS_TRIGGER = 0.01
P4_P95_ABS_TRIGGER = 0.02
P5_MIN_ELIGIBLE_DAYS = 40
# Default σ/τ band when the caller does not pass ``band``.
DEFAULT_P5_BAND: tuple[float, float] = (0.5, 1.5)
P6_EPS = 1e-12  # absolute notional, not relative to equity


@dataclass(frozen=True)
class RolGateResult(GateResult):
    """GateResult plus P1 diagnostics. ``passed`` / ``reasons`` keep the report shape."""

    completion: tuple[tuple[str, Any], ...] = ()
    missing: tuple[str, ...] = ()

    def completion_dict(self) -> dict[str, Any]:
        return dict(self.completion)


def class_defaults() -> dict[str, Any]:
    """HK/CN quality-book ``__init__`` defaults (I_strong=0.95, ρ=risk_off_scale)."""
    from quantit.strategy.hk_book import HKQualityBookStrategy

    sig = inspect.signature(HKQualityBookStrategy.__init__)
    out: dict[str, Any] = {}
    for key in REQUIRED_YAML_KEYS:
        param = sig.parameters.get(key)
        if param is not None and param.default is not inspect.Parameter.empty:
            out[key] = param.default
    return out


def p3_weight_cap(n_target: int) -> float:
    """Per-name |w| cap from the *target* quality universe size."""
    n = int(n_target)
    if n <= 0:
        return 0.0
    return min(P3_WEIGHT_CAP_NUMERATOR / float(n) + P3_WEIGHT_CAP_ADD, P3_WEIGHT_CAP_ABS_MAX)


def missing_yaml_keys(params: Mapping[str, Any] | None) -> tuple[str, ...]:
    """Required keys absent from YAML (after rho ↔ risk_off_scale aliasing)."""
    have = {str(k) for k in (params or {})}
    if "tau" in have:
        have.add("target_vol")
    if "rho" in have or "risk_off_scale" in have:
        have.add("rho")
        have.add("risk_off_scale")
    return tuple(key for key in REQUIRED_YAML_KEYS if key not in have)


def completion_vector(params: Mapping[str, Any] | None) -> dict[str, Any]:
    """P1 补全向量: YAML ∪ class defaults (full vector, not the missing-key list)."""
    defaults = class_defaults()
    raw = {str(k): v for k, v in dict(params or {}).items()}
    if "tau" in raw and "target_vol" not in raw:
        raw["target_vol"] = raw["tau"]
    if "risk_off_scale" in raw:
        raw["rho"] = raw["risk_off_scale"]
    elif "rho" in raw:
        raw["risk_off_scale"] = raw["rho"]
    filled = dict(defaults)
    filled.update(raw)
    if "risk_off_scale" in filled:
        filled["rho"] = filled["risk_off_scale"]
    return filled


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


def _has_label(value: Any) -> bool:
    if value is None:
        return False
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    if isinstance(value, float) and not np.isfinite(value):
        return False
    return True


def _truthy(value: Any) -> bool:
    if not _has_label(value):
        return False
    return bool(value)


def _format_completion(filled: Mapping[str, Any]) -> str:
    keys = list(REQUIRED_YAML_KEYS)
    if "rho" in filled and "rho" not in keys:
        keys.append("rho")
    parts = [f"{key}={filled[key]}" for key in keys if key in filled]
    extras = [f"{k}={v}" for k, v in filled.items() if k not in keys]
    return " ".join(parts + extras)


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
) -> RolGateResult:
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
    filled = completion_vector(yaml_params)
    missing = missing_yaml_keys(yaml_params) if yaml_params is not None else ()
    print("P1 completion vector: " + _format_completion(filled))
    if missing:
        print("P1 missing: " + ", ".join(missing))
        reasons.append("P1 completion vector: " + _format_completion(filled))
        reasons.append("missing yaml keys: " + ", ".join(missing))

    i_strong = float(filled["invested_strong"])
    rho = float(filled["risk_off_scale"])

    # --- R1 paper halt ≠ report max_dd ---------------------------------------
    for raw in (paper_halt, halt_threshold):
        if raw is None:
            continue
        if abs(float(raw) - PAPER_HALT) > 1e-12:
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

    # --- P2 lag-1 labels; risk-on G≤I_strong, risk-off G≤ρ -------------------
    lagged = None
    if labels is not None or trading_days is not None:
        lagged = lag1_trading_labels(labels, trading_days, holidays, suspensions)
    holiday_block = {_norm_ts(d) for d in (holidays or [])} | {
        _norm_ts(d) for d in (suspensions or [])
    }
    for day, gross, _w in _gross_rows(weights):
        if day is not None and day in holiday_block:
            continue
        cap: float | None = None
        regime = ""
        if lagged is not None and day is not None and day in lagged.index:
            label = lagged.loc[day]
            if _has_label(label):
                if _truthy(label):
                    cap, regime = i_strong, "risk-on"
                else:
                    cap, regime = rho, "risk-off"
        if cap is not None and gross > cap + 1e-12:
            reasons.append(
                f"P2 lag-1 {regime} G=Σ|w| {gross:.4f} exceeds {cap:.4f} "
                f"(I_strong={i_strong:.4f}, rho={rho:.4f})"
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

    # --- P4 median×1.5 and P95×2.5; abs floors only if baseline is tiny ------
    metric = _as_float_list(metric_series)
    baseline = _as_float_list(baseline_series)
    if metric is not None and baseline is not None and metric and baseline:
        med = float(np.median(metric))
        base_med = float(np.median(baseline))
        p95 = float(np.quantile(metric, 0.95))
        base_p95 = float(np.quantile(baseline, 0.95))
        if base_med < P4_MEDIAN_ABS_TRIGGER:
            median_limit = P4_MEDIAN_ABS
        else:
            median_limit = P4_MEDIAN_MULT * base_med
        if base_p95 < P4_P95_ABS_TRIGGER:
            p95_limit = P4_P95_ABS
        else:
            p95_limit = P4_P95_MULT * base_p95
        median_ok = med <= median_limit + 1e-12
        p95_ok = p95 <= p95_limit + 1e-12
        if not median_ok or not p95_ok:
            reasons.append(
                f"P4 median {med:.4f} vs limit {median_limit:.4f} "
                f"({P4_MEDIAN_MULT}× baseline {base_med:.4f}, "
                f"abs {P4_MEDIAN_ABS:.2f} only if median(T̄)<{P4_MEDIAN_ABS_TRIGGER}); "
                f"P95 {p95:.4f} vs limit {p95_limit:.4f} "
                f"({P4_P95_MULT}× baseline P95 {base_p95:.4f}, "
                f"abs {P4_P95_ABS:.2f} only if P95(T̄)<{P4_P95_ABS_TRIGGER})"
            )

    # --- P5 eligible-day evidence --------------------------------------------
    mask = _as_bool_list(eligible_mask)
    band_lo_hi = DEFAULT_P5_BAND if band is None else (float(band[0]), float(band[1]))
    if mask is not None:
        n_eligible = int(sum(mask))
        if declared_eligible_days is not None and int(declared_eligible_days) != n_eligible:
            n_eligible = min(n_eligible, int(declared_eligible_days))
            if int(declared_eligible_days) >= P5_MIN_ELIGIBLE_DAYS and n_eligible < P5_MIN_ELIGIBLE_DAYS:
                n_eligible = min(n_eligible, P5_MIN_ELIGIBLE_DAYS - 1)
        if n_eligible < P5_MIN_ELIGIBLE_DAYS:
            reasons.append(
                "P5 rol_evidence=incomplete; incomplete invalidates the whole "
                "study evidence pack"
            )
        elif metric is not None:
            lo, hi = band_lo_hi
            paired = list(zip(mask, metric))
            if any(flag and (val < lo - 1e-12 or val > hi + 1e-12) for flag, val in paired):
                reasons.append(f"P5 band breach outside [{lo:.4f}, {hi:.4f}] (σ/τ)")
        else:
            lo, hi = band_lo_hi
            reasons.append(f"P5 band [{lo:.4f}, {hi:.4f}] requires metric_series")

    # --- P6 unlabeled derivatives (absolute ε, not relative to equity) -------
    if float(unlabeled_derivative_notional) > P6_EPS:
        reasons.append(
            f"P6 unlabeled derivative notional {float(unlabeled_derivative_notional):.3g} "
            f"> ε={P6_EPS:g} (absolute ε, not relative to equity)"
        )

    return RolGateResult(
        passed=not reasons,
        reasons=tuple(reasons),
        completion=tuple(filled.items()),
        missing=tuple(missing),
    )
