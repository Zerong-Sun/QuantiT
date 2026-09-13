"""Research broker costs: CN_PROFILE buy vs sell+stamp (paper schedule)."""

from __future__ import annotations

import pandas as pd
import pytest

from quantit.engine.broker import Broker, OrderStatus
from quantit.engine.portfolio import Portfolio
from quantit.markets.cn import CN_PROFILE
from quantit.utils.config import get_config


def _cn_broker(cash: float = 1_000_000.0) -> Broker:
    return Broker(
        Portfolio(initial_cash=cash),
        commission_rate=CN_PROFILE.commission_rate,
        slippage_rate=CN_PROFILE.slippage_rate,
        stamp_duty_rate=CN_PROFILE.stamp_duty_rate,
        venue="cn",
    )


class TestCNResearchFills:
    def test_cn_buy_commission_is_profile_rate_without_stamp(self) -> None:
        broker = _cn_broker()
        price = 10.0
        qty = 100
        order = broker.buy("600519.SS", qty, price, pd.Timestamp("2024-06-10"))
        assert order.status == OrderStatus.FILLED
        fill = price * (1 + CN_PROFILE.slippage_rate)
        notional = fill * qty
        assert order.commission == pytest.approx(notional * CN_PROFILE.commission_rate)
        assert order.commission == pytest.approx(notional * 0.0003)

    def test_cn_equity_sell_commission_adds_stamp(self) -> None:
        broker = _cn_broker()
        price = 10.0
        qty = 100
        buy = broker.buy("600519.SS", qty, price, pd.Timestamp("2024-06-10"))
        assert buy.status == OrderStatus.FILLED
        sell = broker.sell("600519.SS", qty, price, pd.Timestamp("2024-06-11"))
        assert sell.status == OrderStatus.FILLED
        fill = price * (1 - CN_PROFILE.slippage_rate)
        notional = fill * qty
        expected_rate = CN_PROFILE.commission_rate + CN_PROFILE.stamp_duty_rate
        assert sell.commission == pytest.approx(notional * expected_rate)
        assert sell.commission == pytest.approx(notional * (0.0003 + 0.0005))

    def test_cn_etf_sell_is_stamp_exempt(self) -> None:
        broker = _cn_broker()
        price = 3.5
        qty = 100
        buy = broker.buy("510300.SS", qty, price, pd.Timestamp("2024-06-10"))
        assert buy.status == OrderStatus.FILLED
        sell = broker.sell("510300.SS", qty, price, pd.Timestamp("2024-06-11"))
        assert sell.status == OrderStatus.FILLED
        fill = price * (1 - CN_PROFILE.slippage_rate)
        notional = fill * qty
        assert sell.commission == pytest.approx(notional * CN_PROFILE.commission_rate)
        assert sell.commission == pytest.approx(notional * 0.0003)


class TestDefaultResearchFills:
    def test_default_path_still_charges_bilateral_config_commission(self) -> None:
        cfg = get_config()
        broker = Broker(Portfolio(initial_cash=10_000.0))
        price = 100.0
        qty = 10
        buy = broker.buy("AAPL", qty, price, pd.Timestamp("2020-01-02"))
        assert buy.status == OrderStatus.FILLED
        buy_fill = price * (1 + cfg.slippage_rate)
        assert buy.commission == pytest.approx(buy_fill * qty * cfg.commission_rate)
        assert cfg.commission_rate == pytest.approx(0.001)

        sell = broker.sell("AAPL", qty, price, pd.Timestamp("2020-01-03"))
        assert sell.status == OrderStatus.FILLED
        sell_fill = price * (1 - cfg.slippage_rate)
        assert sell.commission == pytest.approx(sell_fill * qty * cfg.commission_rate)

    def test_explicit_zero_commission_stays_zero_both_sides(self) -> None:
        broker = Broker(Portfolio(initial_cash=10_000.0), commission_rate=0.0, slippage_rate=0.0)
        buy = broker.buy("AAPL", 10, 100.0, pd.Timestamp("2020-01-02"))
        sell = broker.sell("AAPL", 10, 110.0, pd.Timestamp("2020-01-03"))
        assert buy.commission == 0.0
        assert sell.commission == 0.0


class TestResearchCostWiring:
    def test_cn_studies_use_cn_profile_schedule(self) -> None:
        from quantit.research.search import research_cost_kwargs

        for strategy_id in ("cn_quality_book", "cn_etf_rotation"):
            kwargs = research_cost_kwargs(strategy_id)
            assert kwargs["commission_rate"] == CN_PROFILE.commission_rate
            assert kwargs["slippage_rate"] == CN_PROFILE.slippage_rate
            assert kwargs["stamp_duty_rate"] == CN_PROFILE.stamp_duty_rate
            assert kwargs["venue"] == "cn"

    def test_us_and_hk_studies_keep_default_broker_costs(self) -> None:
        from quantit.research.search import research_cost_kwargs

        for strategy_id in ("tsmom", "us_book", "hk_quality_book", "theme_rotation"):
            assert research_cost_kwargs(strategy_id) == {}
