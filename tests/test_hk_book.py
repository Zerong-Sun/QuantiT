"""Equal-weight HK quality basket TSMOM (synthetic data, no network)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from quantit.engine.backtester import Backtester
from quantit.research.gates import evaluate_gates
from quantit.research.params import hk_primary, load_active_params
from quantit.research.promote import maybe_promote
from quantit.research.universes import HK_QUALITY
from quantit.research.walk_forward import walk_forward
from quantit.strategy.hk_book import (
    HKQualityBookStrategy,
    equal_weight_index,
    invested_fraction,
    quality_sleeve,
    vol_scale,
)


def _ohlcv(prices: list[float], start: str = "2018-01-01") -> pd.DataFrame:
    dates = pd.date_range(start, periods=len(prices), freq="B")
    return pd.DataFrame(
        {
            "open": prices,
            "high": [p + 0.5 for p in prices],
            "low": [max(0.1, p - 0.5) for p in prices],
            "close": prices,
            "volume": [1_000_000.0] * len(prices),
        },
        index=dates,
    )


def _book(n: int = 400, start_price: float = 100.0, step: float = 0.3) -> dict[str, pd.DataFrame]:
    a = [start_price + i * step for i in range(n)]
    b = [start_price * 0.8 + i * step * 0.9 for i in range(n)]
    return {"0002.HK": _ohlcv(a), "0005.HK": _ohlcv(b)}


def test_equal_weight_index_rises_with_members() -> None:
    book = _book(n=10, step=1.0)
    idx = equal_weight_index(book)
    assert idx.iloc[-1] > idx.iloc[0]


def test_invested_fraction_risk_off() -> None:
    assert invested_fraction(0.1, invested_on=0.95, risk_off_scale=0.5) == pytest.approx(0.95)
    assert invested_fraction(-0.1, invested_on=0.95, risk_off_scale=0.5) == pytest.approx(0.5)
    assert invested_fraction(-0.1, invested_on=0.95, risk_off_scale=0.0) == pytest.approx(0.0)


def test_uptrend_holds_names() -> None:
    book = _book(n=400, step=0.4)
    result = Backtester(initial_cash=1_000_000, commission_rate=0.0, slippage_rate=0.0).run(
        HKQualityBookStrategy(
            lookback=126,
            skip=21,
            risk_off_scale=0.0,
            invested_on=0.95,
            universe=("0002.HK", "0005.HK"),
        ),
        book,
        symbol="HK-QUALITY-BOOK",
    )
    assert result.portfolio.get_position("0002.HK").quantity > 0
    assert result.portfolio.get_position("0005.HK").quantity > 0


def test_downtrend_scale_zero_exits() -> None:
    book = _book(n=400, start_price=200.0, step=-0.4)
    result = Backtester(initial_cash=1_000_000, commission_rate=0.0, slippage_rate=0.0).run(
        HKQualityBookStrategy(
            lookback=126,
            skip=21,
            risk_off_scale=0.0,
            invested_on=0.95,
            universe=("0002.HK", "0005.HK"),
        ),
        book,
        symbol="HK-QUALITY-BOOK",
    )
    assert result.portfolio.get_position("0002.HK").quantity == 0
    assert result.portfolio.get_position("0005.HK").quantity == 0


def test_downtrend_scale_keeps_stub() -> None:
    book = _book(n=400, start_price=200.0, step=-0.4)
    cash = Backtester(initial_cash=1_000_000, commission_rate=0.0, slippage_rate=0.0).run(
        HKQualityBookStrategy(
            lookback=126,
            skip=21,
            risk_off_scale=0.0,
            universe=("0002.HK", "0005.HK"),
        ),
        book,
        symbol="HK-QUALITY-BOOK",
    )
    stub = Backtester(initial_cash=1_000_000, commission_rate=0.0, slippage_rate=0.0).run(
        HKQualityBookStrategy(
            lookback=126,
            skip=21,
            risk_off_scale=0.5,
            universe=("0002.HK", "0005.HK"),
        ),
        book,
        symbol="HK-QUALITY-BOOK",
    )
    assert cash.portfolio.get_position("0002.HK").quantity == 0
    assert stub.portfolio.get_position("0002.HK").quantity + stub.portfolio.get_position("0005.HK").quantity > 0


def test_promote_writes_hk_primary_keeps_us(tmp_path: Path) -> None:
    from quantit.research.params import write_active_params

    write_active_params(
        {"us_primary": "tsmom", "strategies": {"tsmom": {"lookback": 252}}},
        path=tmp_path / "active_params.yaml",
    )
    gate = evaluate_gates(oos_sharpe=0.4, oos_drawdown=-0.1, oos_trades=20, buy_hold_sharpe=0.3)
    from quantit.research.gates import evaluate_promote_gates
    from quantit.research.walk_forward import FoldResult

    def _bear(oos_dd: float, bh_dd: float) -> FoldResult:
        return FoldResult(
            train=slice(0, 1),
            test=slice(1, 2),
            params={},
            is_metrics={},
            oos_metrics={"sharpe_ratio": 0.4, "max_drawdown": oos_dd, "total_trades": 8},
            bh_metrics={"sharpe_ratio": -0.2, "max_drawdown": bh_dd},
            regime="bear",
        )

    promo = evaluate_promote_gates(
        oos_sharpe=0.4,
        oos_drawdown=-0.1,
        oos_trades=20,
        buy_hold_sharpe=0.3,
        buy_hold_drawdown=-0.2,
        folds=[_bear(-0.08, -0.40), _bear(-0.09, -0.30)],
    )
    path = maybe_promote(
        "hk_quality_book",
        {"lookback": 252, "skip": 21, "risk_off_scale": 0.5},
        gate,
        path=tmp_path / "active_params.yaml",
        promote_gate=promo,
    )
    assert path is not None
    payload = load_active_params(path)
    assert payload["hk_primary"] == "hk_quality_book"
    assert payload["us_primary"] == "tsmom"
    assert payload["strategies"]["hk_quality_book"]["skip"] == 21
    assert hk_primary(path) == "hk_quality_book"


def test_walk_forward_synthetic_basket() -> None:
    n = 220
    book = _book(n=n, step=0.3)
    study = walk_forward(
        "hk_quality_book",
        book,
        symbol="HK-QUALITY-BOOK",
        train=80,
        test=40,
        step=40,
        grid=[{"lookback": 40, "skip": 5, "risk_off_scale": 0.5}],
        initial_cash=1_000_000,
    )
    assert study.folds
    assert study.strategy_id == "hk_quality_book"


def test_universe_tuple_is_quality_book() -> None:
    assert "0700.HK" not in HK_QUALITY
    assert "0005.HK" in HK_QUALITY


def test_vol_scale_caps_at_one_and_shrinks_when_hot() -> None:
    assert vol_scale(0.10, target_vol=0.15) == 1.0
    assert vol_scale(0.30, target_vol=0.15) == pytest.approx(0.5)
    assert vol_scale(None, target_vol=0.15) == 1.0
    assert vol_scale(float("nan"), target_vol=0.15) == 1.0
    assert vol_scale(float("inf"), target_vol=0.15) == 0.0
    assert vol_scale(0.30, target_vol=float("nan")) == 1.0
    assert vol_scale(0.30, target_vol=0.0) == 1.0


def test_high_realized_vol_holds_less_than_unscaled() -> None:
    dates = pd.date_range("2018-01-01", periods=400, freq="B")
    noisy = [100.0]
    for i in range(1, 400):
        noisy.append(noisy[-1] * (1.05 if i % 2 == 0 else 0.99))

    def frame(prices: list[float]) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "open": prices,
                "high": [p + 0.5 for p in prices],
                "low": [max(0.1, p - 0.5) for p in prices],
                "close": prices,
                "volume": [1_000_000.0] * len(prices),
            },
            index=dates,
        )

    hot = {"0002.HK": frame(noisy), "0005.HK": frame(noisy)}
    asof = dates[-1]
    frac_tight, mom = quality_sleeve(
        hot,
        lookback=126,
        skip=21,
        invested_on=0.95,
        risk_off_scale=0.0,
        target_vol=0.15,
        vol_lookback=20,
        vol_floor=0.05,
        asof=asof,
    )
    frac_loose, _ = quality_sleeve(
        hot,
        lookback=126,
        skip=21,
        invested_on=0.95,
        risk_off_scale=0.0,
        target_vol=5.0,
        vol_lookback=20,
        vol_floor=0.05,
        asof=asof,
    )
    assert mom is not None and mom > 0
    assert frac_loose == pytest.approx(0.95)
    assert 0 < frac_tight < frac_loose

    tight_run = Backtester(initial_cash=1_000_000, commission_rate=0.0, slippage_rate=0.0).run(
        HKQualityBookStrategy(
            lookback=126, skip=21, risk_off_scale=0.0, target_vol=0.15, universe=("0002.HK", "0005.HK")
        ),
        hot,
        symbol="HK-QUALITY-BOOK",
    )
    loose_run = Backtester(initial_cash=1_000_000, commission_rate=0.0, slippage_rate=0.0).run(
        HKQualityBookStrategy(
            lookback=126, skip=21, risk_off_scale=0.0, target_vol=5.0, universe=("0002.HK", "0005.HK")
        ),
        hot,
        symbol="HK-QUALITY-BOOK",
    )
    marks = {s: float(hot[s]["close"].iloc[-1]) for s in hot}
    tight_eq = tight_run.portfolio.equity(marks)
    loose_eq = loose_run.portfolio.equity(marks)
    tight_invested = tight_eq - tight_run.portfolio.cash
    loose_invested = loose_eq - loose_run.portfolio.cash
    assert tight_invested / tight_eq < loose_invested / loose_eq


def test_walk_forward_defaults_hk_cash_to_paper_size(monkeypatch: pytest.MonkeyPatch) -> None:
    from quantit.paper.capital import PAPER_CASH
    from quantit.research.walk_forward import default_research_cash

    assert default_research_cash("hk_quality_book") == PAPER_CASH["hk"]
    assert default_research_cash("theme_rotation") == PAPER_CASH["hk"]
    assert default_research_cash("tsmom") == PAPER_CASH["us"]

    seen: dict[str, float] = {}

    def fake_grid_search(strategy_id, data, symbol, grid=None, initial_cash=100_000.0, extra=None):
        seen["cash"] = initial_cash
        raise ValueError("stop after recording cash")

    monkeypatch.setattr("quantit.research.walk_forward.grid_search", fake_grid_search)
    walk_forward("hk_quality_book", _book(n=220, step=0.3), symbol="HK-QUALITY-BOOK", train=80, test=40, step=40)
    assert seen["cash"] == PAPER_CASH["hk"]


def test_catalog_exposes_quality_vol_params() -> None:
    from quantit.strategy.catalog import get_strategy

    for strategy_id in ("hk_quality_book", "cn_quality_book"):
        entry = get_strategy(strategy_id)
        assert entry is not None
        names = {p["name"] for p in entry["parameters"]}
        assert {"target_vol", "vol_lookback", "vol_floor", "weighting"} <= names


def test_hk_defaults_keep_target_vol_and_inv_vol() -> None:
    strat = HKQualityBookStrategy()
    assert strat.target_vol == pytest.approx(0.15)
    assert strat.weighting == "inv_vol"
    assert strat.risk_off_scale == pytest.approx(0.5)
    positional = HKQualityBookStrategy(252, 21, 0.5, 0.95, 0.02, 0.15, 20, 0.05, ("0002.HK", "0005.HK"))
    assert positional.universe == ("0002.HK", "0005.HK")
    assert positional.weighting == "inv_vol"


def test_inv_vol_weights_give_less_to_hot_name() -> None:
    from quantit.strategy.hk_book import inv_vol_weights

    weights = inv_vol_weights(["A", "B"], {"A": 0.10, "B": 0.40}, sleeve=0.95)
    assert weights["A"] > weights["B"]
    assert sum(weights.values()) == pytest.approx(0.95)
    assert weights["A"] / weights["B"] == pytest.approx(4.0)


def test_inv_vol_missing_vol_uses_median_not_floor() -> None:
    from quantit.strategy.hk_book import inv_vol_weights

    weights = inv_vol_weights(["A", "B", "C"], {"A": 0.10, "B": 0.30, "C": None}, sleeve=0.90)
    # median(0.10, 0.30) = 0.20 → inv 10, 3.333, 5
    assert weights["C"] == pytest.approx(0.90 * 5.0 / (10.0 + 10.0 / 3.0 + 5.0))
    assert weights["A"] > weights["C"] > weights["B"]
    floor_as_known = inv_vol_weights(["A", "B", "C"], {"A": 0.10, "B": 0.30, "C": 0.05}, sleeve=0.90)
    assert weights["C"] < floor_as_known["C"]


def test_inv_vol_inf_vol_gets_zero_weight() -> None:
    from quantit.strategy.hk_book import inv_vol_weights

    weights = inv_vol_weights(["A", "B"], {"A": 0.10, "B": float("inf")}, sleeve=0.95)
    assert "B" not in weights
    assert weights["A"] == pytest.approx(0.95)
    assert inv_vol_weights(["A"], {"A": float("inf")}, sleeve=0.95) == {}
    assert inv_vol_weights(["A", "B"], {"A": None, "B": None}, sleeve=0.90) == {
        "A": pytest.approx(0.45),
        "B": pytest.approx(0.45),
    }
    assert inv_vol_weights(["A"], {"A": 0.2}, float("nan")) == {}


def test_invalid_weighting_raises() -> None:
    with pytest.raises(ValueError, match="weighting"):
        HKQualityBookStrategy(weighting="hrp")


def test_quality_name_targets_shrinks_hot_name() -> None:
    from quantit.strategy.hk_book import quality_name_targets

    dates = pd.date_range("2018-01-01", periods=80, freq="B")

    def frame(prices: list[float]) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "open": prices,
                "high": [p + 0.5 for p in prices],
                "low": [max(0.1, p - 0.5) for p in prices],
                "close": prices,
                "volume": [1_000_000.0] * len(prices),
            },
            index=dates,
        )

    calm = [100.0 + i * 0.05 for i in range(80)]
    noisy = [100.0]
    for i in range(1, 80):
        noisy.append(noisy[-1] * (1.04 if i % 2 == 0 else 0.97))
    book = {"0002.HK": frame(calm), "0005.HK": frame(noisy)}
    weights = quality_name_targets(
        book,
        ["0002.HK", "0005.HK"],
        0.95,
        dates[-1],
        vol_lookback=20,
        vol_floor=0.05,
        weighting="inv_vol",
    )
    assert weights["0002.HK"] > weights["0005.HK"]
    assert sum(weights.values()) == pytest.approx(0.95)

    equal = quality_name_targets(
        book,
        ["0002.HK", "0005.HK"],
        0.95,
        dates[-1],
        vol_lookback=20,
        vol_floor=0.05,
        weighting="equal",
    )
    assert equal["0002.HK"] == pytest.approx(equal["0005.HK"])


def test_inv_vol_backtest_holds_less_of_noisy_name() -> None:
    dates = pd.date_range("2018-01-01", periods=400, freq="B")

    def frame(prices: list[float]) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "open": prices,
                "high": [p + 0.5 for p in prices],
                "low": [max(0.1, p - 0.5) for p in prices],
                "close": prices,
                "volume": [1_000_000.0] * len(prices),
            },
            index=dates,
        )

    calm = [100.0 + i * 0.2 for i in range(400)]
    noisy = [100.0]
    for i in range(1, 400):
        noisy.append(noisy[-1] * (1.03 if i % 2 == 0 else 0.985))
    book = {"0002.HK": frame(calm), "0005.HK": frame(noisy)}
    result = Backtester(initial_cash=1_000_000, commission_rate=0.0, slippage_rate=0.0).run(
        HKQualityBookStrategy(
            lookback=126,
            skip=21,
            risk_off_scale=0.0,
            target_vol=5.0,
            weighting="inv_vol",
            universe=("0002.HK", "0005.HK"),
        ),
        book,
        symbol="HK-QUALITY-BOOK",
    )
    marks = {s: float(book[s]["close"].iloc[-1]) for s in book}
    equity = result.portfolio.equity(marks)
    calm_w = result.portfolio.get_position("0002.HK").quantity * marks["0002.HK"] / equity
    noisy_w = result.portfolio.get_position("0005.HK").quantity * marks["0005.HK"] / equity
    assert calm_w > noisy_w
