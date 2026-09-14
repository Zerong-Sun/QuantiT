"""ROL v0.1.1 gates: evaluate_rol_gates only. Not wired to --promote."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from quantit.paper.capital import PAPER_MAX_DRAWDOWN
from quantit.research.gates import GateResult, evaluate_gates, evaluate_rol_gates
from quantit.research.params import write_active_params
from quantit.research.rol import (
    DEFAULT_P5_BAND,
    P3_WEIGHT_CAP_ABS_MAX,
    P3_WEIGHT_CAP_ADD,
    P3_WEIGHT_CAP_NUMERATOR,
    P4_P95_ABS,
    P4_P95_ABS_TRIGGER,
    P4_P95_MULT,
    P5_MIN_ELIGIBLE_DAYS,
    P6_EPS,
    PAPER_HALT,
    REPORT_MAX_DRAWDOWN,
    REQUIRED_YAML_KEYS,
    class_defaults,
    completion_vector,
    missing_yaml_keys,
    p3_weight_cap,
)


def _complete_yaml(**overrides: object) -> dict[str, object]:
    params: dict[str, object] = {
        "lookback": 252,
        "skip": 21,
        "target_vol": 0.15,  # τ
        "risk_off_scale": 0.70,  # ρ live key
        "vol_lookback": 20,
        "strong_mom": 0.20,
        "invested_on": 0.90,
        "invested_strong": 0.95,
    }
    params.update(overrides)
    return params


def _clean_kwargs(**overrides: object) -> dict[str, object]:
    """Inputs that pass every ROL check so a test can break one at a time."""
    kwargs: dict[str, object] = {
        "yaml_params": _complete_yaml(),
        "target_universe": [f"N{i}" for i in range(10)],
        "weights": {"N0": 0.09, "N1": 0.09, "N2": 0.09},
        "unlabeled_derivative_notional": 0.0,
        "eligible_mask": [True] * 40,
        "band": (0.0, 1.0),
        "metric_series": [0.02] * 40,
        "baseline_series": [0.02] * 40,
    }
    kwargs.update(overrides)
    return kwargs


def test_1_missing_yaml_keys_completion_vector_and_rescue_knobs_stay_red(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """P1: completion_vector is YAML∪defaults; missing still FAIL. R1: knobs cannot rescue."""
    missing = evaluate_rol_gates(**_clean_kwargs(yaml_params={"lookback": 252}))
    assert isinstance(missing, GateResult)
    assert missing.passed is False
    vector = completion_vector({"lookback": 252})
    defaults = class_defaults()
    assert vector["lookback"] == 252
    assert vector["skip"] == defaults["skip"]
    assert vector["target_vol"] == defaults["target_vol"]
    assert vector["risk_off_scale"] == defaults["risk_off_scale"]
    assert vector["rho"] == defaults["risk_off_scale"]
    absent = missing_yaml_keys({"lookback": 252})
    assert "skip" in absent
    assert "target_vol" in absent
    assert "risk_off_scale" in absent
    assert "lookback" not in absent
    assert absent == missing.missing
    printed = capsys.readouterr().out
    assert "skip" in printed
    assert "target_vol" in printed or "τ" in printed or "tau" in printed
    assert "risk_off_scale" in printed or "rho" in printed or "ρ" in printed
    assert str(defaults["skip"]) in printed
    blob = " ".join(missing.reasons)
    assert "skip" in blob
    assert "missing" in blob.lower()

    rho_only = _complete_yaml()
    rho_only.pop("risk_off_scale")
    rho_only["rho"] = 0.30
    assert missing_yaml_keys(rho_only) == ()
    aliased = completion_vector(rho_only)
    assert aliased["risk_off_scale"] == pytest.approx(0.30)
    assert aliased["rho"] == pytest.approx(0.30)
    live_only = _complete_yaml()
    assert "rho" not in live_only
    assert missing_yaml_keys(live_only) == ()
    assert completion_vector(live_only)["rho"] == live_only["risk_off_scale"]

    fail = evaluate_rol_gates(
        **_clean_kwargs(unlabeled_derivative_notional=1.0),
    )
    assert fail.passed is False

    rescued = evaluate_rol_gates(
        **_clean_kwargs(
            unlabeled_derivative_notional=1.0,
            yaml_params=_complete_yaml(
                lookback=10,
                skip=0,
                target_vol=0.50,
                risk_off_scale=0.99,
                vol_lookback=5,
                strong_mom=0.0,
                invested_on=1.0,
                invested_strong=1.0,
            ),
            lookback=10,
            skip=0,
            tau=0.50,
            rho=0.99,
            vol_lookback=5,
            strong_mom=0.0,
            invested_on=1.0,
            invested_strong=1.0,
            extra_unnamed_knob=123,
        ),
    )
    assert rescued.passed is False
    assert isinstance(rescued, GateResult)


def test_2_labels_use_lag1_not_same_day() -> None:
    """P2/R4: lag-1 trading calendar; risk-on G≤I_strong, risk-off G≤ρ."""
    wed, holiday, suspension, monday = pd.to_datetime(
        ["2024-07-03", "2024-07-04", "2024-07-05", "2024-07-08"]
    )
    trading_days = [wed, holiday, suspension, monday]
    # Wednesday risk-off; Monday same-day risk-on. Lag-1 jumps holiday+suspension,
    # so Monday inherits Wednesday's risk-off and G must use ρ not I_strong.
    labels = pd.Series({wed: 0, holiday: 0, suspension: 0, monday: 1})
    names = [f"N{i}" for i in range(11)]
    # Monday G=11*0.08=0.88:  ρ=0.70 < 0.88 < I_strong=0.95. Same-day would PASS.
    weights = pd.DataFrame(
        {name: [0.04, 0.04, 0.04, 0.08] for name in names},
        index=pd.DatetimeIndex([wed, holiday, suspension, monday]),
    )
    result = evaluate_rol_gates(
        **_clean_kwargs(
            weights=weights,
            labels=labels,
            trading_days=trading_days,
            holidays=[holiday],
            suspensions=[suspension],
            target_universe=names[:10],
        )
    )
    assert result.passed is False
    blob = " ".join(result.reasons).lower()
    assert "p2" in blob
    assert "risk-off" in blob or "rho" in blob
    assert all("P3" not in r for r in result.reasons)

    same_day_would_skip = evaluate_rol_gates(
        **_clean_kwargs(
            weights=pd.DataFrame({"A": [0.09]}, index=pd.DatetimeIndex([monday])),
            labels=pd.Series({monday: 0}),
            trading_days=[monday],
            target_universe=["A"] + [f"N{i}" for i in range(9)],
        )
    )
    # Isolated Monday with no prior session: no lag-1 label, do not apply G-cap.
    assert same_day_would_skip.passed is True


def test_3_shrinking_universe_must_not_raise_p3_cap() -> None:
    """P3: n = |target quality universe| is fixed; cap = min(1/n+0.05, 0.40)."""
    target = [f"N{i}" for i in range(10)]
    held = target[:5]
    cap_target = p3_weight_cap(len(target))
    cap_shrunk = p3_weight_cap(len(held))
    assert cap_target == pytest.approx(
        min(P3_WEIGHT_CAP_NUMERATOR / 10 + P3_WEIGHT_CAP_ADD, P3_WEIGHT_CAP_ABS_MAX)
    )
    assert cap_target == pytest.approx(0.15)
    assert cap_shrunk == pytest.approx(0.25)
    assert cap_shrunk > cap_target
    assert p3_weight_cap(2) == pytest.approx(P3_WEIGHT_CAP_ABS_MAX)

    # 0.20 is above 0.15 (n=10) but below 0.25 (n=5) — must FAIL when n stays at 10.
    weights = {name: 0.20 for name in held}
    result = evaluate_rol_gates(
        **_clean_kwargs(
            target_universe=target,
            held_universe=held,
            weights=weights,
        )
    )
    assert result.passed is False
    assert any("P3" in r or "cap" in r.lower() for r in result.reasons)
    equal_ok = evaluate_rol_gates(
        **_clean_kwargs(
            target_universe=target,
            held_universe=held,
            weights={name: 0.09 for name in held},
        )
    )
    assert equal_ok.passed is True


def test_4_low_median_high_p95_p4_fail() -> None:
    """P4/R2: median×1.5 and P95×2.5. Abs 0.10 only if P95(T̄)<0.02 — no fishing OR."""
    baseline = [0.02] * 100
    series = [0.02] * 90 + [0.40] * 10
    result = evaluate_rol_gates(
        **_clean_kwargs(
            metric_series=series,
            baseline_series=baseline,
            eligible_mask=[True] * 100,
            band=(0.0, 1.0),
        )
    )
    assert result.passed is False
    blob = " ".join(result.reasons).lower()
    assert "p4" in blob
    assert "p95" in blob
    assert any("2.5" in r or "p95" in r.lower() for r in result.reasons)

    # Unconditional p95≤0.10 would pass this tail (0.09≤0.10); 2.5×0.03=0.075 must FAIL.
    quiet_base = [0.03] * 100
    fish = [0.03] * 90 + [0.09] * 10
    fished = evaluate_rol_gates(
        **_clean_kwargs(
            metric_series=fish,
            baseline_series=quiet_base,
            eligible_mask=[True] * 100,
            band=(0.0, 1.0),
        )
    )
    assert fished.passed is False
    assert "p95" in " ".join(fished.reasons).lower()
    assert P4_P95_ABS == pytest.approx(0.10)
    assert P4_P95_ABS_TRIGGER == pytest.approx(0.02)
    assert P4_P95_MULT == pytest.approx(2.5)


def test_5_eligible_days_incomplete_and_band_fail() -> None:
    """P5/R3: <40 ⇒ incomplete voids the pack; ≥40 with band breach ⇒ FAIL."""
    assert DEFAULT_P5_BAND == (0.5, 1.5)
    incomplete = evaluate_rol_gates(
        **_clean_kwargs(
            eligible_mask=[True] * (P5_MIN_ELIGIBLE_DAYS - 1),
            metric_series=[0.5] * (P5_MIN_ELIGIBLE_DAYS - 1),
            baseline_series=[0.5] * (P5_MIN_ELIGIBLE_DAYS - 1),
            band=(0.0, 1.0),
        )
    )
    assert incomplete.passed is False
    blob = " ".join(incomplete.reasons).lower()
    assert "incomplete" in blob
    assert "pack" in blob or "evidence" in blob

    subset = evaluate_rol_gates(
        **_clean_kwargs(
            eligible_mask=[True] * 39,
            metric_series=[0.5] * 39,
            baseline_series=[0.5] * 39,
            band=(0.0, 1.0),
            declared_eligible_days=50,
        )
    )
    assert subset.passed is False
    assert "incomplete" in " ".join(subset.reasons).lower()

    breached = evaluate_rol_gates(
        **_clean_kwargs(
            eligible_mask=[True] * 40,
            metric_series=[0.5] * 39 + [9.0],
            baseline_series=[0.5] * 40,
            band=(0.0, 1.0),
        )
    )
    assert breached.passed is False
    assert "incomplete" not in " ".join(breached.reasons).lower()
    assert any("P5" in r or "band" in r.lower() for r in breached.reasons)


def test_6_cl_fills_yaml_write_is_noop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When cl has fills, writing US/HK/CN YAML is a no-op (desk isolation)."""
    us = tmp_path / "us.yaml"
    hk = tmp_path / "hk.yaml"
    cn = tmp_path / "cn.yaml"
    originals = {"us": "us: keep\n", "hk": "hk: keep\n", "cn": "cn: keep\n"}
    us.write_text(originals["us"], encoding="utf-8")
    hk.write_text(originals["hk"], encoding="utf-8")
    cn.write_text(originals["cn"], encoding="utf-8")

    writes: list[object] = []

    def _forbid_write(payload: object, path: object = None) -> Path:
        writes.append((payload, path))
        raise AssertionError("ROL must not write YAML")

    monkeypatch.setattr("quantit.research.params.write_active_params", _forbid_write)
    monkeypatch.setattr("quantit.research.promote.maybe_promote", lambda *a, **k: (_ for _ in ()).throw(AssertionError("ROL must not call maybe_promote")))

    result = evaluate_rol_gates(
        **_clean_kwargs(
            cl_has_fills=True,
            yaml_paths={"us": us, "hk": hk, "cn": cn},
            attempt_write_yaml=True,
        )
    )
    assert writes == []
    assert us.read_text(encoding="utf-8") == originals["us"]
    assert hk.read_text(encoding="utf-8") == originals["hk"]
    assert cn.read_text(encoding="utf-8") == originals["cn"]
    assert isinstance(result, GateResult)
    assert result.passed is True


def test_7_unlabeled_derivative_notional_fail() -> None:
    """P6: unlabeled derivative notionals > ε ⇒ FAIL. ε is absolute, not % equity."""
    assert P6_EPS == pytest.approx(1e-12)
    labeled_ok = evaluate_rol_gates(
        **_clean_kwargs(
            unlabeled_derivative_notional=0.0,
            labeled_derivative_notional=1_000.0,
        )
    )
    assert labeled_ok.passed is True

    unlabeled = evaluate_rol_gates(
        **_clean_kwargs(unlabeled_derivative_notional=1e-6),
    )
    assert unlabeled.passed is False
    blob = " ".join(unlabeled.reasons).lower()
    assert "p6" in blob or "derivative" in blob
    assert "absolute" in blob or "not relative" in blob


def test_8_paper_halt_not_interchangeable_with_report_max_dd() -> None:
    """R1: paper halt 0.20 ≠ report max_dd −0.25; not substitutable."""
    assert PAPER_HALT == pytest.approx(0.20)
    assert PAPER_MAX_DRAWDOWN == pytest.approx(0.20)
    assert REPORT_MAX_DRAWDOWN == pytest.approx(-0.25)
    assert PAPER_HALT != abs(REPORT_MAX_DRAWDOWN)

    report = evaluate_gates(
        oos_sharpe=0.5,
        oos_drawdown=-0.22,
        oos_trades=20,
        buy_hold_sharpe=0.1,
        buy_hold_drawdown=-0.30,
    )
    assert report.passed is True, "−0.22 clears report max_dd −0.25"

    rol = evaluate_rol_gates(
        **_clean_kwargs(max_drawdown=-0.22),
    )
    assert rol.passed is False, "paper halt 0.20 must fire; report −0.25 must not be used"
    blob = " ".join(rol.reasons).lower()
    assert "0.20" in blob or "halt" in blob
    assert "-0.25" not in blob or "not" in blob

    swapped = evaluate_rol_gates(
        **_clean_kwargs(
            max_drawdown=-0.22,
            paper_halt=0.25,
            halt_threshold=0.25,
        ),
    )
    assert swapped.passed is False
    swapped_blob = " ".join(swapped.reasons).lower()
    assert "halt" in swapped_blob
    assert "interchange" in swapped_blob or "not" in swapped_blob


def test_evaluate_rol_gates_not_aliased_to_report_or_promote() -> None:
    from quantit.research.gates import evaluate_promote_gates

    assert evaluate_rol_gates is not evaluate_gates
    assert evaluate_rol_gates is not evaluate_promote_gates
    assert evaluate_gates.__defaults__[-1] == 4.0
    report = evaluate_gates.__defaults__
    assert report[-2] == pytest.approx(-0.25)
    assert callable(write_active_params)
    assert set(REQUIRED_YAML_KEYS) >= {"risk_off_scale", "invested_strong"}
    assert DEFAULT_P5_BAND == (0.5, 1.5)
