"""Walk-forward research engine (synthetic data, no network)."""

from __future__ import annotations

from pathlib import Path
import math

import pandas as pd
import pytest

from quantit.research.gates import evaluate_gates, fold_regime
from quantit.research.params import clear_params_cache, load_active_params
from quantit.research.promote import maybe_promote
from quantit.research.search import grid_search
from quantit.research.walk_forward import iter_folds, walk_forward


def _trend(n: int = 200, start: str = "2018-01-01") -> pd.DataFrame:
    dates = pd.date_range(start, periods=n, freq="B")
    prices = [100.0 * (1.002 ** i) for i in range(n)]
    return pd.DataFrame(
        {
            "open": prices,
            "high": [p + 0.3 for p in prices],
            "low": [p - 0.3 for p in prices],
            "close": prices,
            "volume": [1_000_000.0] * n,
        },
        index=dates,
    )


def test_iter_folds_count() -> None:
    folds = list(iter_folds(n=200, train=80, test=40, step=40))
    assert folds
    train0, test0 = folds[0]
    assert train0.stop - train0.start == 80
    assert test0.stop - test0.start == 40
    assert test0.start == train0.stop


def test_grid_search_picks_a_param_set() -> None:
    data = _trend(180)
    best = grid_search(
        "tsmom",
        data,
        symbol="AAA",
        grid=[{"lookback": 40, "skip": 5, "target_vol": 0.15, "vol_lookback": 10}],
        initial_cash=100_000,
    )
    assert best["params"]["lookback"] == 40
    assert "sharpe_ratio" in best["metrics"]


def test_walk_forward_records_oos() -> None:
    data = _trend(220)
    study = walk_forward(
        "tsmom",
        data,
        symbol="AAA",
        train=80,
        test=40,
        step=40,
        grid=[{"lookback": 40, "skip": 5, "target_vol": 0.15, "vol_lookback": 10}],
    )
    assert study.folds
    assert study.oos_sharpe == pytest.approx(
        sum(f.oos_metrics["sharpe_ratio"] for f in study.folds) / len(study.folds)
    )
    assert all(math.isfinite(f.oos_metrics["sharpe_ratio"]) for f in study.folds)
    assert sum(f.oos_metrics["total_trades"] for f in study.folds) > 0


def test_gates_fail_does_not_promote(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QUANTIT_ACTIVE_PARAMS", str(tmp_path / "active_params.yaml"))
    clear_params_cache()
    gate = evaluate_gates(
        oos_sharpe=-0.2,
        oos_drawdown=-0.4,
        oos_trades=1,
        buy_hold_sharpe=0.5,
    )
    assert not gate.passed
    written = maybe_promote(
        strategy_id="tsmom",
        params={"lookback": 252},
        gate=gate,
        path=tmp_path / "active_params.yaml",
    )
    assert written is None
    assert load_active_params(tmp_path / "active_params.yaml") == {}


def test_promote_tsmom_writes_yaml(tmp_path: Path) -> None:
    gate = evaluate_gates(
        oos_sharpe=1.2,
        oos_drawdown=-0.1,
        oos_trades=20,
        buy_hold_sharpe=0.4,
    )
    assert gate.passed
    path = maybe_promote(
        strategy_id="tsmom",
        params={"lookback": 252, "skip": 21, "target_vol": 0.15},
        gate=gate,
        path=tmp_path / "active_params.yaml",
    )
    assert path is not None
    payload = load_active_params(path)
    assert payload["us_primary"] == "tsmom"
    assert payload["strategies"]["tsmom"]["lookback"] == 252


def test_gate_allows_lagging_buy_hold_when_drawdown_ok() -> None:
    gate = evaluate_gates(
        oos_sharpe=0.4,
        oos_drawdown=-0.12,
        oos_trades=10,
        buy_hold_sharpe=1.1,
        buy_hold_drawdown=-0.20,
    )
    assert gate.passed


def test_gate_fails_non_positive_sharpe() -> None:
    gate = evaluate_gates(
        oos_sharpe=0.0,
        oos_drawdown=-0.05,
        oos_trades=10,
        buy_hold_sharpe=1.0,
        buy_hold_drawdown=-0.40,
    )
    assert not gate.passed


def test_gate_drawdown_ok_if_better_than_buy_hold() -> None:
    gate = evaluate_gates(
        oos_sharpe=0.5,
        oos_drawdown=-0.30,
        oos_trades=10,
        buy_hold_sharpe=-0.2,
        buy_hold_drawdown=-0.40,
    )
    assert gate.passed


def test_fold_regime_tags() -> None:
    assert fold_regime(0.8) == "bull"
    assert fold_regime(-0.1) == "bear"
    assert fold_regime(0.2) == "flat"


def test_us_book_cannot_promote(tmp_path: Path) -> None:
    gate = evaluate_gates(
        oos_sharpe=1.2,
        oos_drawdown=-0.1,
        oos_trades=20,
        buy_hold_sharpe=0.4,
    )
    assert (
        maybe_promote(
            strategy_id="us_book",
            params={"fast_period": 10, "slow_period": 30},
            gate=gate,
            path=tmp_path / "active_params.yaml",
        )
        is None
    )


def test_ma_signal_reads_promoted_params() -> None:
    from quantit.research.params import write_active_params
    from quantit.strategy.signals import ma_signal

    write_active_params({"strategies": {"ma_crossover": {"fast_period": 5, "slow_period": 20}}})
    n = 40
    dates = pd.date_range("2024-01-02", periods=n, freq="B")
    prices = [100.0] * n
    bars = pd.DataFrame(
        {
            "open": prices,
            "high": [p + 1 for p in prices],
            "low": [p - 1 for p in prices],
            "close": prices,
            "volume": [1_000_000.0] * n,
        },
        index=dates,
    )
    sig = ma_signal(bars)
    assert sig["values"]["fast_period"] == 5
    assert sig["values"]["slow_period"] == 20


def test_walk_forward_too_short_fails_gate() -> None:
    data = _trend(20)
    study = walk_forward("tsmom", data, symbol="AAA", train=80, test=40, step=40)
    assert study.folds == []
    assert not study.passed
    assert study.gate is not None
    assert any("enough bars" in r.lower() or "not enough" in r.lower() for r in study.gate.reasons)


def test_walk_forward_empty_dict_does_not_crash() -> None:
    study = walk_forward("theme_rotation", {}, symbol="HK", train=80, test=40, step=40, extra={"scores": pd.DataFrame()})
    assert study.folds == []
    assert not study.passed
    cn = walk_forward(
        "cn_etf_rotation",
        {},
        symbol="CN",
        train=80,
        test=40,
        step=40,
        extra={"scores": pd.DataFrame()},
    )
    assert cn.folds == []
    assert not cn.passed
    hk = walk_forward("hk_quality_book", {}, symbol="HK", train=80, test=40, step=40)
    assert hk.folds == []
    assert not hk.passed
    cn = walk_forward("cn_quality_book", {}, symbol="CN", train=80, test=40, step=40)
    assert cn.folds == []
    assert not cn.passed


def test_cn_etf_rotation_walk_forward_synthetic() -> None:
    from quantit.research.specs import get_spec

    spec = get_spec("cn_etf_rotation")
    assert spec.kind == "multi"
    assert spec.promote is False

    n = 220
    names = ("512480.SS", "515030.SS", "510300.SS")
    ohlcv = {sym: _trend(n) for sym in names}
    idx = next(iter(ohlcv.values())).index
    scores = pd.DataFrame(
        {"semis": 1.0, "ev": 0.4, "healthcare": 0.2, "defense": 0.1},
        index=idx,
    )
    study = walk_forward(
        "cn_etf_rotation",
        ohlcv,
        symbol="CN-ETF-ROTATION",
        train=80,
        test=40,
        step=40,
        grid=[{"cash_threshold": -0.5, "risk_off_invested": 0.4}],
        extra={"scores": scores},
    )
    assert study.folds
    assert math.isfinite(study.oos_sharpe)


def test_hk_quality_book_spec_is_promotable() -> None:
    from quantit.research.specs import get_spec

    spec = get_spec("hk_quality_book")
    assert spec.kind == "multi"
    assert spec.promote is True
    assert spec.extra_keys == ()
    assert len(spec.grid) == 6


def test_cn_quality_book_spec_is_promotable() -> None:
    from quantit.research.specs import get_spec

    spec = get_spec("cn_quality_book")
    assert spec.kind == "multi"
    assert spec.promote is True
    assert spec.extra_keys == ()
    assert len(spec.grid) == 6


def test_buy_and_hold_equal_weight_multi() -> None:
    from quantit.engine.backtester import Backtester
    from quantit.research.search import EqualWeightHold, buy_and_hold_metrics

    a = _trend(40)
    b = _trend(40)
    result = Backtester(initial_cash=100_000, commission_rate=0.0, slippage_rate=0.0).run(
        EqualWeightHold(), {"AAA": a, "BBB": b}, symbol="BASKET"
    )
    assert result.portfolio.get_position("AAA").quantity > 0
    assert result.portfolio.get_position("BBB").quantity > 0
    metrics = buy_and_hold_metrics({"AAA": a, "BBB": b}, "BASKET")
    assert "sharpe_ratio" in metrics


def test_walk_forward_aligns_multi_asset_by_date() -> None:
    long = _trend(100, start="2020-01-01")
    short = _trend(40, start="2020-03-02")
    scores = pd.DataFrame({"platforms": 1.0}, index=long.index.union(short.index).sort_values())
    from quantit.research.search import slice_by_dates
    from quantit.research.walk_forward import calendar_index

    cal = calendar_index({"AAA": long, "BBB": short})
    train_dates = cal[:30]
    sliced = slice_by_dates({"AAA": long, "BBB": short}, train_dates)
    aaa_dates = set(sliced["AAA"].index)
    bbb_dates = set(sliced.get("BBB", pd.DataFrame()).index) if "BBB" in sliced else set()
    assert aaa_dates
    assert aaa_dates <= set(train_dates)
    assert bbb_dates <= set(train_dates)
    extra = slice_by_dates(scores, train_dates)
    assert set(extra.index) <= set(train_dates)


def test_params_reload_after_file_appears(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "active_params.yaml"
    monkeypatch.setenv("QUANTIT_ACTIVE_PARAMS", str(path))
    clear_params_cache()
    assert load_active_params() == {}
    path.write_text("us_primary: tsmom\nstrategies:\n  tsmom:\n    lookback: 126\n", encoding="utf-8")
    loaded = load_active_params()
    assert loaded["us_primary"] == "tsmom"


def test_tsmom_report_includes_us_book_column() -> None:
    from quantit.research.report import render_study

    data = _trend(220)
    study = walk_forward(
        "tsmom",
        data,
        symbol="AAA",
        train=80,
        test=40,
        step=40,
        grid=[{"lookback": 40, "skip": 5, "target_vol": 0.15, "vol_lookback": 10}],
    )
    html = render_study(study)
    assert "US book" in html or "us_book" in html
    assert "OOS window" in html
    assert "Regime" in html
    assert study.folds[0].us_book_metrics
    assert study.folds[0].test_start
    assert study.folds[0].regime in {"bull", "bear", "flat"}
    assert study.bh_drawdown <= 0


def test_write_folds_csv_has_regime_columns(tmp_path: Path) -> None:
    from quantit.research.report import write_folds_csv

    data = _trend(220)
    study = walk_forward(
        "tsmom",
        data,
        symbol="AAA",
        train=80,
        test=40,
        step=40,
        grid=[{"lookback": 40, "skip": 5, "target_vol": 0.15, "vol_lookback": 10}],
    )
    dest = tmp_path / "folds.csv"
    write_folds_csv(study, dest)
    text = dest.read_text(encoding="utf-8")
    header = text.splitlines()[0]
    for col in ("test_start", "test_end", "regime", "oos_calmar", "bh_dd"):
        assert col in header


def test_default_research_symbols_are_us_quality() -> None:
    from quantit.research.universes import US_QUALITY, default_research_symbols

    assert default_research_symbols() == list(US_QUALITY)
    assert "NVDA" not in default_research_symbols()
    assert "QQQ" not in default_research_symbols()
