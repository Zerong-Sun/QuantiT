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
from quantit.strategy.hk_book import HKQualityBookStrategy, equal_weight_index, invested_fraction


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
