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
    def test_cn_profile_is_3bp_commission_5bp_stamp_5bp_slip(self) -> None:
        assert CN_PROFILE.commission_rate == pytest.approx(0.0003)
        assert CN_PROFILE.stamp_duty_rate == pytest.approx(0.0005)
        assert CN_PROFILE.slippage_rate == pytest.approx(0.0005)

    def test_cn_buy_commission_is_profile_rate_without_stamp(self) -> None:
        broker = _cn_broker()
        price = 10.0
        qty = 100
        order = broker.buy("600519.SS", qty, price, pd.Timestamp("2024-06-10"))
        assert order.status == OrderStatus.FILLED
        fill = price * (1 + CN_PROFILE.slippage_rate)
        notional = fill * qty
        assert order.fill_price == pytest.approx(fill)
        assert order.commission == pytest.approx(notional * CN_PROFILE.commission_rate)
        assert order.commission == pytest.approx(notional * 0.0003)
        # Not the old bilateral 10 bp proxy, and not a flat 8 bp (3+5) both ways.
        assert order.commission != pytest.approx(notional * 0.001)
        assert order.commission != pytest.approx(notional * 0.0008)

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
        assert sell.fill_price == pytest.approx(fill)
        assert sell.commission == pytest.approx(notional * expected_rate)
        assert sell.commission == pytest.approx(notional * (0.0003 + 0.0005))
        assert sell.commission != pytest.approx(notional * 0.0003)
        assert sell.commission != pytest.approx(notional * 0.001)

    def test_cn_buy_and_sell_are_asymmetric_not_bilateral_proxy(self) -> None:
        broker = _cn_broker()
        price = 10.0
        qty = 100
        buy = broker.buy("600519.SS", qty, price, pd.Timestamp("2024-06-10"))
        sell = broker.sell("600519.SS", qty, price, pd.Timestamp("2024-06-11"))
        buy_notional = buy.fill_price * qty
        sell_notional = sell.fill_price * qty
        buy_rate = buy.commission / buy_notional
        sell_rate = sell.commission / sell_notional
        assert buy_rate == pytest.approx(0.0003)
        assert sell_rate == pytest.approx(0.0008)
        assert sell_rate > buy_rate

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
        assert sell.commission != pytest.approx(notional * 0.0008)

    def test_cn_etf_sell_sizing_excludes_stamp(self) -> None:
        broker = _cn_broker()
        slip_comm = CN_PROFILE.slippage_rate + CN_PROFILE.commission_rate
        assert broker.sell_cost_ratio_for("510300.SS") == pytest.approx(slip_comm)
        assert broker.sell_cost_ratio_for("600519.SS") == pytest.approx(
            slip_comm + CN_PROFILE.stamp_duty_rate
        )


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

    def test_run_backtest_tsmom_keeps_bilateral_10bp(self) -> None:
        from quantit.engine.broker import OrderSide
        from quantit.research.search import run_backtest

        dates = pd.date_range("2018-01-01", periods=80, freq="B")
        prices = [100.0 * (1.002 ** i) for i in range(80)]
        data = pd.DataFrame(
            {
                "open": prices,
                "high": [p + 0.3 for p in prices],
                "low": [p - 0.3 for p in prices],
                "close": prices,
                "volume": [1_000_000.0] * 80,
            },
            index=dates,
        )
        row = run_backtest(
            "tsmom",
            {"lookback": 40, "skip": 5, "target_vol": 0.15, "vol_lookback": 10},
            data,
            symbol="AAA",
            initial_cash=100_000.0,
        )
        trades = row["result"].trades
        assert trades
        for trade in trades:
            rate = 0.001
            assert trade.commission == pytest.approx(trade.price * trade.quantity * rate)
            if trade.side == OrderSide.SELL:
                assert trade.commission != pytest.approx(trade.price * trade.quantity * 0.0008)

    def test_buy_and_hold_metrics_dict_ohlcv_smoke(self) -> None:
        from quantit.research.search import buy_and_hold_metrics

        dates = pd.date_range("2018-01-01", periods=30, freq="B")
        prices = [50.0 + i * 0.1 for i in range(30)]
        frame = pd.DataFrame(
            {
                "open": prices,
                "high": [p + 0.2 for p in prices],
                "low": [p - 0.2 for p in prices],
                "close": prices,
                "volume": [1_000_000.0] * 30,
            },
            index=dates,
        )
        metrics = buy_and_hold_metrics(
            {"AAA": frame, "BBB": frame.copy()},
            "BASKET",
            initial_cash=100_000.0,
        )
        assert "sharpe_ratio" in metrics
        assert "max_drawdown" in metrics
        assert metrics["total_trades"] >= 1

    def test_buy_and_hold_metrics_multi_asset_uses_EqualWeightHold(self) -> None:
        import inspect

        from quantit.research.search import EqualWeightHold, buy_and_hold_metrics, research_cost_kwargs

        src = inspect.getsource(buy_and_hold_metrics)
        assert "EqualWeightHold()" in src or "EqualWeightHold" in src
        assert "equalWeightHold()" not in src

        dates = pd.date_range("2018-01-01", periods=40, freq="B")
        prices = [100.0 + i * 0.2 for i in range(40)]
        frame = pd.DataFrame(
            {
                "open": prices,
                "high": [p + 0.3 for p in prices],
                "low": [p - 0.3 for p in prices],
                "close": prices,
                "volume": [1_000_000.0] * 40,
            },
            index=dates,
        )
        book = {"600519.SS": frame, "600036.SS": frame.copy()}
        metrics = buy_and_hold_metrics(book, "CN-BH", initial_cash=1_000_000.0, **research_cost_kwargs("cn_quality_book"))
        assert "sharpe_ratio" in metrics
        assert metrics["total_trades"] >= 1
        assert EqualWeightHold.__name__ == "EqualWeightHold"

    def test_report_gate_defaults_unchanged(self) -> None:
        import inspect

        from quantit.research.gates import evaluate_gates, evaluate_promote_gates

        report = inspect.signature(evaluate_gates)
        assert report.parameters["min_sharpe"].default == 0.0
        assert report.parameters["max_drawdown"].default == -0.25
        assert report.parameters["min_trades"].default == 4.0
        promote = inspect.signature(evaluate_promote_gates)
        assert promote.parameters["min_sharpe"].default == 0.0
        assert promote.parameters["max_drawdown"].default == -0.25
        assert promote.parameters["min_trades"].default == 4.0
