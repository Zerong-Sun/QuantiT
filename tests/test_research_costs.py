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

    def test_run_backtest_cn_quality_charges_profile_on_fills(self) -> None:
        from quantit.engine.broker import OrderSide
        from quantit.research.search import run_backtest

        n = 80
        dates = pd.date_range("2018-01-01", periods=n, freq="B")

        def _ohlcv(start: float, step: float) -> pd.DataFrame:
            prices = [start + i * step for i in range(n)]
            return pd.DataFrame(
                {
                    "open": prices,
                    "high": [p + 0.5 for p in prices],
                    "low": [max(0.1, p - 0.5) for p in prices],
                    "close": prices,
                    "volume": [1_000_000.0] * n,
                },
                index=dates,
            )

        book = {"600519.SS": _ohlcv(100.0, 0.4), "600036.SS": _ohlcv(80.0, 0.36)}
        row = run_backtest(
            "cn_quality_book",
            {"lookback": 40, "skip": 5, "risk_off_scale": 0.5},
            book,
            symbol="CN",
            initial_cash=1_000_000.0,
        )
        trades = row["result"].trades
        buys = [t for t in trades if t.side == OrderSide.BUY]
        sells = [t for t in trades if t.side == OrderSide.SELL]
        assert buys
        for trade in buys:
            assert trade.commission == pytest.approx(trade.price * trade.quantity * 0.0003)
        for trade in sells:
            assert trade.commission == pytest.approx(trade.price * trade.quantity * (0.0003 + 0.0005))
