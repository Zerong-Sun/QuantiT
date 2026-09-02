"""Paper runner, seed cash, and allowed asset classes."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from quantit.data.provider import DataProvider
from quantit.markets.assets import asset_class, is_allowed, multiplier, us_option_root
from quantit.markets.cn import CNAdapter
from quantit.markets.hk import HKAdapter
from quantit.markets.registry import MarketRegistry
from quantit.markets.us import USAdapter
from quantit.paper.broker import PaperBroker
from quantit.paper.capital import PAPER_CASH
from quantit.paper.db import create_session
from quantit.paper.runner import PaperRunner


def _ohlcv(n: int = 80, start: str = "2024-01-02", start_price: float = 100.0, step: float = 0.4) -> pd.DataFrame:
    dates = pd.date_range(start, periods=n, freq="B")
    prices = [start_price + i * step for i in range(n)]
    return pd.DataFrame(
        {
            "open": prices,
            "high": [p + 1 for p in prices],
            "low": [p - 1 for p in prices],
            "close": prices,
            "volume": [1_000_000.0] * n,
        },
        index=dates,
    )


class FakeProvider(DataProvider):
    def __init__(self, frames: dict[str, pd.DataFrame]) -> None:
        self.frames = frames

    def fetch(self, symbol, start, end, interval: str = "1d") -> pd.DataFrame:
        if symbol not in self.frames:
            raise ValueError(f"No data returned for {symbol}")
        return self.frames[symbol].copy()


def _registry(frames: dict[str, pd.DataFrame] | None = None) -> MarketRegistry:
    frames = frames or {
        "AAPL": _ohlcv(start_price=150.0, step=-1.0),
        "0700.HK": _ohlcv(start_price=300.0),
        "600519.SS": _ohlcv(start_price=10.0, step=0.05),
        "AAPL250117C00150000": _ohlcv(n=5, start_price=5.0, step=0.0),
        "14993.HK": _ohlcv(n=5, start_price=0.2, step=0.0),
        "2800.HK": _ohlcv(start_price=20.0),
        "SPY": _ohlcv(start_price=400.0),
    }
    registry = MarketRegistry()
    registry.register(USAdapter(provider=FakeProvider(frames)))
    registry.register(HKAdapter(provider=FakeProvider(frames)))
    registry.register(CNAdapter(provider=FakeProvider(frames)))
    return registry


class TestAssetClasses:
    def test_us_option_and_etf(self) -> None:
        assert asset_class("us", "AAPL") == "equity"
        assert asset_class("us", "SPY") == "etf"
        assert asset_class("us", "AAPL250117C00150000") == "option"
        assert multiplier("us", "AAPL250117C00150000") == 100
        assert is_allowed("us", "AAPL250117C00150000")
        assert not is_allowed("hk", "AAPL250117C00150000")
        assert us_option_root("AAPL250117C00150000") == "AAPL"
        assert us_option_root("AAPL") is None

    def test_hk_warrant_and_etf(self) -> None:
        assert asset_class("hk", "0700.HK") == "equity"
        assert asset_class("hk", "2800.HK") == "etf"
        assert asset_class("hk", "14993.HK") == "warrant"
        assert is_allowed("hk", "14993")
        assert is_allowed("hk", "3033.HK")
        from quantit.paper.capital import HK_WARRANT_WATCHLIST

        assert HK_WARRANT_WATCHLIST == ("27882.HK", "13606.HK", "14567.HK")

    def test_cn_etf_and_equity(self) -> None:
        assert asset_class("cn", "600519.SS") == "equity"
        assert asset_class("cn", "510300.SS") == "etf"
        assert asset_class("cn", "159915.SZ") == "etf"
        assert asset_class("cn", "158003.SZ") == "etf"
        assert asset_class("cn", "512480.SS") == "etf"
        assert is_allowed("cn", "510300.SS")
        assert is_allowed("cn", "600519.SS")


class TestSeedCash:
    def test_default_seeds(self) -> None:
        session = create_session("sqlite:///:memory:")
        broker = PaperBroker(session, registry=_registry(), now=lambda: datetime(2024, 6, 10, 10, 0, 0))
        broker.ensure_accounts()
        cash = {a.market_id: a.cash for a in broker.list_accounts()}
        assert cash["us"] == PAPER_CASH["us"]
        assert cash["hk"] == PAPER_CASH["hk"]
        assert cash["cn"] == PAPER_CASH["cn"]

    def test_seed_increase_tops_up_open_book(self) -> None:
        session = create_session("sqlite:///:memory:")
        broker = PaperBroker(session, registry=_registry(), now=lambda: datetime(2024, 6, 10, 10, 0, 0))
        broker.ensure_accounts(cash=50_000.0)
        broker.place_order("us", "AAPL", "buy", 1)
        us_cash = broker.get_account("us").cash
        assert broker.get_position("us", "AAPL") is not None
        broker.ensure_accounts()
        us = broker.get_account("us")
        assert us.initial_cash == PAPER_CASH["us"]
        assert us.cash == pytest.approx(us_cash + (PAPER_CASH["us"] - 50_000.0))
        assert broker.get_position("us", "AAPL") is not None
        hk = broker.get_account("hk")
        assert hk.cash == PAPER_CASH["hk"]
        assert hk.initial_cash == PAPER_CASH["hk"]


class TestAllowedOrders:
    def test_us_option_uses_100_multiplier(self) -> None:
        session = create_session("sqlite:///:memory:")
        broker = PaperBroker(session, registry=_registry(), now=lambda: datetime(2024, 6, 10, 10, 0, 0))
        broker.ensure_accounts()
        before = broker.get_account("us").cash
        order = broker.place_order("us", "AAPL250117C00150000", "buy", 1)
        assert order.status == "filled"
        # last 5.0, slippage 0.05%, multiplier 100
        assert order.fill_price == pytest.approx(5.0 * 1.0005)
        spent = before - broker.get_account("us").cash
        assert spent == pytest.approx(order.fill_price * 100)

    def test_hk_warrant_fills(self) -> None:
        session = create_session("sqlite:///:memory:")
        broker = PaperBroker(session, registry=_registry(), now=lambda: datetime(2024, 6, 10, 10, 0, 0))
        broker.ensure_accounts()
        order = broker.place_order("hk", "14993", "buy", 1000)
        assert order.status == "filled"


class TestRunner:
    def test_buys_oversold_us_name_once_per_day(self) -> None:
        session = create_session("sqlite:///:memory:")
        broker = PaperBroker(session, registry=_registry(), now=lambda: datetime(2024, 6, 10, 10, 0, 0))
        broker.ensure_accounts()
        runner = PaperRunner(broker, us_watch=("AAPL",), hk_scores=None)
        first = runner.tick()
        buys = [a for a in first if a["side"] == "buy" and a["status"] == "filled"]
        assert buys
        assert buys[0]["symbol"] == "AAPL"
        pos = broker.get_position("us", "AAPL")
        assert pos is not None and pos.quantity > 0
        again = runner.tick()
        assert again == []

    def test_buys_uptrend_without_waiting_for_cross(self) -> None:
        frames = {
            "AAPL": _ohlcv(start_price=100.0, step=0.8),
            "0700.HK": _ohlcv(start_price=300.0),
            "600519.SS": _ohlcv(start_price=10.0, step=0.05),
        }
        session = create_session("sqlite:///:memory:")
        broker = PaperBroker(
            session, registry=_registry(frames), now=lambda: datetime(2024, 6, 10, 10, 0, 0)
        )
        broker.ensure_accounts()
        runner = PaperRunner(broker, us_watch=("AAPL",), hk_scores=None)
        first = runner.tick()
        buys = [a for a in first if a["side"] == "buy" and a["status"] == "filled"]
        assert buys and buys[0]["symbol"] == "AAPL"

    def test_api_runner_and_accounts(self) -> None:
        from quantit.api.app import create_app

        registry = _registry()
        session = create_session("sqlite:///:memory:")
        broker = PaperBroker(session, registry=registry, now=lambda: datetime(2024, 6, 10, 10, 0, 0))
        runner = PaperRunner(broker, us_watch=("AAPL",), hk_scores=None)
        app = create_app(broker=broker, registry=registry, runner=runner)
        client = TestClient(app)
        accounts = {a["market_id"]: a for a in client.get("/api/v1/accounts").json()}
        assert accounts["us"]["cash"] == pytest.approx(100_000)
        assert accounts["hk"]["cash"] == pytest.approx(1_000_000)
        assert accounts["cn"]["cash"] == pytest.approx(1_000_000)
        us = next(m for m in client.get("/api/v1/markets").json() if m["id"] == "us")
        assert set(us["allowed_asset_classes"]) == {"equity", "etf", "option"}
        hk = next(m for m in client.get("/api/v1/markets").json() if m["id"] == "hk")
        assert set(hk["allowed_asset_classes"]) == {"equity", "etf", "warrant"}
        cn = next(m for m in client.get("/api/v1/markets").json() if m["id"] == "cn")
        assert set(cn["allowed_asset_classes"]) == {"equity", "etf"}
        inst = client.get("/api/v1/instrument", params={"market": "us", "symbol": "SPY"}).json()
        assert inst["asset_class"] == "etf"
        body = client.post("/api/v1/runner/tick").json()
        assert body["actions"]
        assert client.get("/api/v1/positions").json()

    def test_buys_us_call_overlay(self) -> None:
        session = create_session("sqlite:///:memory:")
        broker = PaperBroker(session, registry=_registry(), now=lambda: datetime(2024, 6, 10, 10, 0, 0))
        broker.ensure_accounts()
        runner = PaperRunner(
            broker,
            us_watch=("AAPL",),
            hk_warrants=(),
            hk_scores=None,
            us_option_picker=lambda _u, _spot, _asof: "AAPL250117C00150000",
        )
        first = runner.tick()
        filled = {a["symbol"] for a in first if a["status"] == "filled"}
        assert "AAPL" in filled
        assert "AAPL250117C00150000" in filled
        opt = broker.get_position("us", "AAPL250117C00150000")
        assert opt is not None and opt.quantity >= 1

    def test_buys_hk_warrant_on_oversold(self) -> None:
        frames = {
            "AAPL": _ohlcv(start_price=150.0, step=-1.0),
            "0700.HK": _ohlcv(start_price=300.0),
            "600519.SS": _ohlcv(start_price=10.0, step=0.05),
            "14993.HK": _ohlcv(start_price=1.0, step=-0.01),
        }
        session = create_session("sqlite:///:memory:")
        broker = PaperBroker(
            session, registry=_registry(frames), now=lambda: datetime(2024, 6, 10, 10, 0, 0)
        )
        broker.ensure_accounts()
        runner = PaperRunner(broker, us_watch=(), hk_warrants=("14993.HK",), hk_scores=None)
        first = runner.tick()
        buys = [a for a in first if a["side"] == "buy" and a["status"] == "filled"]
        assert any(a["symbol"] == "14993.HK" for a in buys)

    def test_hk_rotation_force_skips_month_end(self) -> None:
        n = 130
        frames = {
            "AAPL": _ohlcv(n=n, start_price=150.0),
            "0700.HK": _ohlcv(n=n, start_price=300.0),
            "1810.HK": _ohlcv(n=n, start_price=20.0),
            "2800.HK": _ohlcv(n=n, start_price=20.0),
            "3033.HK": _ohlcv(n=n, start_price=5.0),
            "600519.SS": _ohlcv(n=n, start_price=10.0, step=0.05),
        }
        idx = frames["0700.HK"].index
        scores = pd.DataFrame(
            {
                "platforms": [1.0] * n,
                "hardware": [0.4] * n,
                "semis": [0.2] * n,
                "ev": [0.1] * n,
            },
            index=idx,
        )
        session = create_session("sqlite:///:memory:")
        broker = PaperBroker(
            session, registry=_registry(frames), now=lambda: datetime(2024, 6, 10, 10, 0, 0)
        )
        broker.ensure_accounts()
        runner = PaperRunner(
            broker,
            us_watch=(),
            hk_etfs=("2800.HK", "3033.HK"),
            hk_warrants=(),
            hk_scores=scores,
        )
        skipped = runner.tick(markets=("hk",), force=False)
        assert skipped == []
        assert broker.get_position("hk", "0700.HK") is None
        forced = runner.tick(markets=("hk",), force=True)
        filled = [a for a in forced if a["status"] == "filled" and a["market_id"] == "hk"]
        assert filled
        assert any("manual" in (a.get("rationale") or "") for a in filled)
        assert broker.get_position("hk", "0700.HK") is not None

    def test_tsmom_primary_buys_uptrend(self) -> None:
        from quantit.research.params import write_active_params

        write_active_params(
            {
                "us_primary": "tsmom",
                "strategies": {"tsmom": {"lookback": 60, "skip": 5, "target_vol": 0.15, "vol_lookback": 20}},
            }
        )
        frames = {
            "AAPL": _ohlcv(n=120, start_price=100.0, step=0.6),
            "0700.HK": _ohlcv(start_price=300.0),
            "600519.SS": _ohlcv(start_price=10.0, step=0.05),
        }
        session = create_session("sqlite:///:memory:")
        broker = PaperBroker(
            session, registry=_registry(frames), now=lambda: datetime(2024, 6, 10, 10, 0, 0)
        )
        broker.ensure_accounts()
        runner = PaperRunner(broker, us_watch=("AAPL",), hk_warrants=(), hk_scores=None)
        first = runner.tick()
        buys = [a for a in first if a["side"] == "buy" and a["status"] == "filled" and a["symbol"] == "AAPL"]
        assert buys
        assert "momentum" in (buys[0].get("rationale") or "").lower() or "time-series" in (
            buys[0].get("rationale") or ""
        ).lower()

    def test_tsmom_nan_vol_falls_back_to_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from quantit.research.params import write_active_params

        write_active_params({"us_primary": "tsmom"})

        def fake_eval(market, symbol, bars):
            return {
                "signals": [
                    {
                        "strategy_id": "tsmom",
                        "action": "buy",
                        "reason": "time-series momentum",
                        "values": {"realized_vol": float("nan"), "target_vol": 0.15},
                    }
                ]
            }

        monkeypatch.setattr("quantit.paper.runner.evaluate_signals", fake_eval)
        frames = {
            "AAPL": _ohlcv(n=80, start_price=100.0, step=0.4),
            "0700.HK": _ohlcv(start_price=300.0),
            "600519.SS": _ohlcv(start_price=10.0, step=0.05),
        }
        session = create_session("sqlite:///:memory:")
        broker = PaperBroker(
            session, registry=_registry(frames), now=lambda: datetime(2024, 6, 10, 10, 0, 0)
        )
        broker.ensure_accounts()
        runner = PaperRunner(broker, us_watch=("AAPL",), hk_warrants=(), hk_scores=None)
        first = runner.tick()
        buys = [a for a in first if a["side"] == "buy" and a["status"] == "filled" and a["symbol"] == "AAPL"]
        assert buys
        pos = broker.get_position("us", "AAPL")
        assert pos is not None and pos.quantity > 0

    def test_tsmom_sell_reduces_to_overlay(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from quantit.research.params import write_active_params

        write_active_params({"us_primary": "tsmom"})

        def fake_eval(market, symbol, bars):
            return {
                "signals": [
                    {
                        "strategy_id": "tsmom",
                        "action": "sell",
                        "reason": "weak momentum overlay",
                        "values": {
                            "risk_off_scale": 0.3,
                            "realized_vol": 0.15,
                            "target_vol": 0.15,
                        },
                    }
                ]
            }

        monkeypatch.setattr("quantit.paper.runner.evaluate_signals", fake_eval)
        frames = {
            "AAPL": _ohlcv(n=80, start_price=150.0, step=0.0),
            "0700.HK": _ohlcv(start_price=300.0),
            "600519.SS": _ohlcv(start_price=10.0, step=0.05),
        }
        session = create_session("sqlite:///:memory:")
        broker = PaperBroker(
            session, registry=_registry(frames), now=lambda: datetime(2024, 6, 10, 10, 0, 0)
        )
        broker.ensure_accounts()
        broker.place_order("us", "AAPL", "buy", 200)
        before = broker.get_position("us", "AAPL").quantity
        runner = PaperRunner(broker, us_watch=("AAPL",), hk_warrants=(), hk_scores=None)
        runner.tick()
        after = broker.get_position("us", "AAPL")
        assert after is not None
        assert 0 < after.quantity < before

    def test_tsmom_sell_flatten_when_scale_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from quantit.research.params import write_active_params

        write_active_params({"us_primary": "tsmom"})

        def fake_eval(market, symbol, bars):
            return {
                "signals": [
                    {
                        "strategy_id": "tsmom",
                        "action": "sell",
                        "reason": "weak momentum cash",
                        "values": {
                            "risk_off_scale": 0.0,
                            "realized_vol": 0.15,
                            "target_vol": 0.15,
                        },
                    }
                ]
            }

        monkeypatch.setattr("quantit.paper.runner.evaluate_signals", fake_eval)
        frames = {
            "AAPL": _ohlcv(n=80, start_price=150.0, step=0.0),
            "0700.HK": _ohlcv(start_price=300.0),
            "600519.SS": _ohlcv(start_price=10.0, step=0.05),
        }
        session = create_session("sqlite:///:memory:")
        broker = PaperBroker(
            session, registry=_registry(frames), now=lambda: datetime(2024, 6, 10, 10, 0, 0)
        )
        broker.ensure_accounts()
        broker.place_order("us", "AAPL", "buy", 50)
        runner = PaperRunner(broker, us_watch=("AAPL",), hk_warrants=(), hk_scores=None)
        runner.tick()
        assert broker.get_position("us", "AAPL") is None


class TestDerivativesPick:
    def test_choose_expiry_in_band(self) -> None:
        from datetime import date

        from quantit.markets.derivatives import choose_expiry

        picked = choose_expiry(["2024-06-07", "2024-08-16", "2025-01-17"], date(2024, 6, 10))
        assert picked == "2024-08-16"

    def test_pick_atm_call(self) -> None:
        from quantit.markets.derivatives import pick_atm_call

        calls = pd.DataFrame(
            {
                "contractSymbol": ["AAPL250117C00140000", "AAPL250117C00150000", "AAPL250117C00160000"],
                "strike": [140.0, 150.0, 160.0],
            }
        )
        assert pick_atm_call(calls, 151.0) == "AAPL250117C00150000"
