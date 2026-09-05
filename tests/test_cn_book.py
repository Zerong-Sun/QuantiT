"""Equal-weight CN quality basket TSMOM (synthetic data, no network)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from quantit.engine.backtester import Backtester
from quantit.research.gates import evaluate_gates
from quantit.research.params import cn_primary, load_active_params
from quantit.research.promote import maybe_promote
from quantit.research.universes import CN_QUALITY
from quantit.research.walk_forward import walk_forward
from quantit.strategy.cn_book import CNQualityBookStrategy


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
    return {"600519.SS": _ohlcv(a), "600036.SS": _ohlcv(b)}


def test_universe_defaults_to_cn_quality() -> None:
    strat = CNQualityBookStrategy()
    assert strat.universe == CN_QUALITY
    assert strat.target_vol == pytest.approx(0.30)
    assert strat.weighting == "inv_vol"
    assert strat.risk_off_scale == pytest.approx(0.5)


def test_catalog_cn_default_target_vol_is_higher_than_hk() -> None:
    from quantit.strategy.catalog import get_strategy

    cn = get_strategy("cn_quality_book")
    hk = get_strategy("hk_quality_book")
    assert cn is not None and hk is not None
    cn_vol = next(p["value"] for p in cn["parameters"] if p["name"] == "target_vol")
    hk_vol = next(p["value"] for p in hk["parameters"] if p["name"] == "target_vol")
    assert cn_vol == pytest.approx(0.30)
    assert hk_vol == pytest.approx(0.15)


def test_cn_yaml_without_target_vol_uses_constructor_default() -> None:
    from quantit.strategy.tsmom import coerce_vol

    defaults = CNQualityBookStrategy()
    cfg: dict = {"lookback": 252, "skip": 0, "risk_off_scale": 0.5}
    target_vol = coerce_vol(cfg.get("target_vol", defaults.target_vol), defaults.target_vol)
    assert target_vol == pytest.approx(0.30)


def test_uptrend_holds_names() -> None:
    book = _book(n=400, step=0.4)
    result = Backtester(initial_cash=1_000_000, commission_rate=0.0, slippage_rate=0.0).run(
        CNQualityBookStrategy(
            lookback=126,
            skip=21,
            risk_off_scale=0.0,
            invested_on=0.95,
            universe=("600519.SS", "600036.SS"),
        ),
        book,
        symbol="CN-QUALITY-BOOK",
    )
    assert result.portfolio.get_position("600519.SS").quantity > 0
    assert result.portfolio.get_position("600036.SS").quantity > 0


def test_downtrend_scale_zero_exits() -> None:
    book = _book(n=400, start_price=200.0, step=-0.4)
    result = Backtester(initial_cash=1_000_000, commission_rate=0.0, slippage_rate=0.0).run(
        CNQualityBookStrategy(
            lookback=126,
            skip=21,
            risk_off_scale=0.0,
            invested_on=0.95,
            universe=("600519.SS", "600036.SS"),
        ),
        book,
        symbol="CN-QUALITY-BOOK",
    )
    assert result.portfolio.get_position("600519.SS").quantity == 0
    assert result.portfolio.get_position("600036.SS").quantity == 0


def test_downtrend_scale_keeps_stub() -> None:
    book = _book(n=400, start_price=200.0, step=-0.4)
    stub = Backtester(initial_cash=1_000_000, commission_rate=0.0, slippage_rate=0.0).run(
        CNQualityBookStrategy(
            lookback=126,
            skip=21,
            risk_off_scale=0.5,
            universe=("600519.SS", "600036.SS"),
        ),
        book,
        symbol="CN-QUALITY-BOOK",
    )
    assert (
        stub.portfolio.get_position("600519.SS").quantity
        + stub.portfolio.get_position("600036.SS").quantity
        > 0
    )


def test_promote_writes_cn_primary_keeps_us_hk(tmp_path: Path) -> None:
    from quantit.research.params import write_active_params

    write_active_params(
        {
            "us_primary": "tsmom",
            "hk_primary": "hk_quality_book",
            "strategies": {"tsmom": {"lookback": 252}},
        },
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
        "cn_quality_book",
        {"lookback": 252, "skip": 21, "risk_off_scale": 0.5},
        gate,
        path=tmp_path / "active_params.yaml",
        promote_gate=promo,
    )
    assert path is not None
    payload = load_active_params(path)
    assert payload["cn_primary"] == "cn_quality_book"
    assert payload["us_primary"] == "tsmom"
    assert payload["hk_primary"] == "hk_quality_book"
    assert payload["strategies"]["cn_quality_book"]["skip"] == 21
    assert cn_primary(path) == "cn_quality_book"


def test_walk_forward_synthetic_basket() -> None:
    n = 220
    book = _book(n=n, step=0.3)
    study = walk_forward(
        "cn_quality_book",
        book,
        symbol="CN-QUALITY-BOOK",
        train=80,
        test=40,
        step=40,
        grid=[{"lookback": 40, "skip": 5, "risk_off_scale": 0.5}],
        initial_cash=1_000_000,
    )
    assert study.folds
    assert study.strategy_id == "cn_quality_book"


def test_universe_tuple_is_quality_book() -> None:
    assert "510300.SS" not in CN_QUALITY
    assert "600519.SS" in CN_QUALITY


def test_walk_forward_defaults_cn_cash_to_paper_size() -> None:
    from quantit.paper.capital import PAPER_CASH
    from quantit.research.walk_forward import default_research_cash

    assert default_research_cash("cn_quality_book") == PAPER_CASH["cn"]
    assert default_research_cash("cn_etf_rotation") == PAPER_CASH["cn"]
