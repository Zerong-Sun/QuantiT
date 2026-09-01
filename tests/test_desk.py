"""Tests for the strategy catalog, live reasons, and notes board."""

from __future__ import annotations

import inspect
from datetime import datetime

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from quantit.data.provider import DataProvider
from quantit.markets.cn import CNAdapter
from quantit.markets.hk import HKAdapter, HSTECH_THEMES
from quantit.markets.registry import MarketRegistry
from quantit.markets.us import USAdapter
from quantit.paper.broker import PaperBroker
from quantit.paper.db import _ensure_columns, create_session
from quantit.strategy.catalog import list_strategies
from quantit.strategy.regime import ThemeRotationStrategy
from quantit.strategy.signals import evaluate_signals, ma_signal, rsi_signal, theme_signal
from quantit.strategy.technical import (
    MACrossoverStrategy,
    RSIMeanReversionStrategy,
    ma_cross_side,
    rsi_reversion_side,
)


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
        self.intervals: list[str] = []

    def fetch(self, symbol, start, end, interval: str = "1d") -> pd.DataFrame:
        self.intervals.append(interval)
        if symbol not in self.frames:
            raise ValueError(f"No data returned for {symbol}")
        return self.frames[symbol].copy()


def _registry() -> MarketRegistry:
    registry = MarketRegistry()
    registry.register(USAdapter(provider=FakeProvider({"AAPL": _ohlcv()})))
    registry.register(HKAdapter(provider=FakeProvider({"0700.HK": _ohlcv(start_price=300.0)})))
    registry.register(CNAdapter(provider=FakeProvider({"600519.SS": _ohlcv(start_price=10.0, step=0.05)})))
    return registry


@pytest.fixture
def client() -> TestClient:
    from quantit.api.app import create_app

    registry = _registry()
    session = create_session("sqlite:///:memory:")
    broker = PaperBroker(session, registry=registry, now=lambda: datetime(2024, 6, 10, 10, 0, 0))
    app = create_app(broker=broker, registry=registry)
    return TestClient(app)


class TestCatalog:
    def test_defaults_match_strategy_classes(self) -> None:
        by_id = {e["id"]: e for e in list_strategies()}
        assert set(by_id) == {"ma_crossover", "rsi_mean_reversion", "theme_rotation"}
        ma = {p["name"]: p["value"] for p in by_id["ma_crossover"]["parameters"]}
        rsi = {p["name"]: p["value"] for p in by_id["rsi_mean_reversion"]["parameters"]}
        theme = {p["name"]: p["value"] for p in by_id["theme_rotation"]["parameters"]}
        defaults = MACrossoverStrategy()
        rsi_defaults = RSIMeanReversionStrategy()
        assert ma["fast_period"] == defaults.fast_period
        assert ma["slow_period"] == defaults.slow_period
        assert rsi["buy_threshold"] == rsi_defaults.buy_threshold
        assert theme["cash_threshold"] == inspect.signature(ThemeRotationStrategy.__init__).parameters["cash_threshold"].default
        assert theme["risk_off_invested"] == inspect.signature(ThemeRotationStrategy.__init__).parameters["risk_off_invested"].default
        assert set(by_id["theme_rotation"]["universe"]) == set(HSTECH_THEMES)
        assert by_id["ma_crossover"]["markets"] == ["us"]
        assert by_id["theme_rotation"]["markets"] == ["hk"]

    def test_api_lists_and_filters(self, client: TestClient) -> None:
        all_rows = client.get("/api/v1/strategies").json()
        assert {r["id"] for r in all_rows} == {"ma_crossover", "rsi_mean_reversion", "theme_rotation"}
        hk = client.get("/api/v1/strategies", params={"market": "hk"}).json()
        assert [r["id"] for r in hk] == ["theme_rotation"]
        one = client.get("/api/v1/strategies/ma_crossover").json()
        assert one["class_name"] == "MACrossoverStrategy"
        missing = client.get("/api/v1/strategies/does-not-exist")
        assert missing.status_code == 404


class TestSignals:
    def test_ma_cross_up(self) -> None:
        n = 40
        dates = pd.date_range("2024-01-02", periods=n, freq="B")
        prices = [100.0] * (n - 1) + [200.0]
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
        assert sig["action"] == "buy"
        assert "crossed above" in sig["reason"]

    def test_ma_cross_down(self) -> None:
        n = 40
        dates = pd.date_range("2024-01-02", periods=n, freq="B")
        prices = [200.0] * (n - 1) + [50.0]
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
        assert sig["action"] == "sell"
        assert "crossed below" in sig["reason"]

    def test_ma_latest_nan_is_not_a_cross(self) -> None:
        n = 40
        dates = pd.date_range("2024-01-02", periods=n, freq="B")
        prices = [100.0] * n
        prices[-1] = float("nan")
        bars = pd.DataFrame(
            {
                "open": prices,
                "high": [101.0] * n,
                "low": [99.0] * n,
                "close": prices,
                "volume": [1_000_000.0] * n,
            },
            index=dates,
        )
        sig = ma_signal(bars)
        assert sig["action"] == "hold"
        assert "not available" in sig["reason"]

    def test_ma_too_few_bars(self) -> None:
        sig = ma_signal(_ohlcv(n=5))
        assert sig["action"] == "hold"
        assert "Need at least" in sig["reason"]

    def test_rsi_oversold(self) -> None:
        n = 40
        dates = pd.date_range("2024-01-02", periods=n, freq="B")
        prices = [100.0 - i * 2.0 for i in range(n)]
        bars = pd.DataFrame(
            {
                "open": prices,
                "high": [p + 0.2 for p in prices],
                "low": [p - 0.2 for p in prices],
                "close": prices,
                "volume": [1_000_000.0] * n,
            },
            index=dates,
        )
        sig = rsi_signal(bars)
        assert sig["action"] == "buy"
        assert "oversold" in sig["reason"]

    def test_rsi_overbought(self) -> None:
        n = 40
        dates = pd.date_range("2024-01-02", periods=n, freq="B")
        prices = [50.0 + i * 3.0 for i in range(n)]
        bars = pd.DataFrame(
            {
                "open": prices,
                "high": [p + 0.2 for p in prices],
                "low": [p - 0.2 for p in prices],
                "close": prices,
                "volume": [1_000_000.0] * n,
            },
            index=dates,
        )
        sig = rsi_signal(bars)
        assert sig["action"] == "sell"
        assert "overbought" in sig["reason"]

    def test_theme_membership(self) -> None:
        inside = theme_signal("0700.HK")
        assert inside["values"]["theme"] == "platforms"
        assert inside["action"] == "watch"
        outside = theme_signal("0005.HK")
        assert outside["action"] == "hold"
        assert "outside" in outside["reason"]

    def test_api_bundle(self, client: TestClient) -> None:
        us = client.get("/api/v1/signals", params={"market": "us", "symbol": "AAPL"}).json()
        ids = {s["strategy_id"] for s in us["signals"]}
        assert ids == {"ma_crossover", "rsi_mean_reversion"}
        assert us["headline"]
        hk = client.get("/api/v1/signals", params={"market": "hk", "symbol": "0700.HK"}).json()
        hk_ids = {s["strategy_id"] for s in hk["signals"]}
        assert hk_ids == {"theme_rotation"}
        theme = next(s for s in hk["signals"] if s["strategy_id"] == "theme_rotation")
        assert theme["values"]["theme"] == "platforms"
        cn = client.get("/api/v1/signals", params={"market": "cn", "symbol": "600519.SS"}).json()
        assert cn["signals"] == []
        assert "No strategy" in cn["headline"]

    def test_signals_always_fetch_daily(self) -> None:
        from quantit.api.app import create_app

        us_provider = FakeProvider({"AAPL": _ohlcv()})
        registry = MarketRegistry()
        registry.register(USAdapter(provider=us_provider))
        session = create_session("sqlite:///:memory:")
        broker = PaperBroker(session, registry=registry, now=lambda: datetime(2024, 6, 10, 10, 0, 0))
        client = TestClient(create_app(broker=broker, registry=registry))
        us_provider.intervals.clear()
        client.get("/api/v1/signals", params={"market": "us", "symbol": "AAPL", "interval": "5m"})
        assert us_provider.intervals == ["1d"]

    def test_evaluate_includes_headline(self) -> None:
        bundle = evaluate_signals("us", "AAPL", _ohlcv())
        assert bundle["symbol"] == "AAPL"
        assert len(bundle["signals"]) == 2
        hk = evaluate_signals("hk", "0700.HK", _ohlcv())
        assert [s["strategy_id"] for s in hk["signals"]] == ["theme_rotation"]
        cn = evaluate_signals("cn", "600519.SS", _ohlcv())
        assert cn["signals"] == []

    def test_shared_cross_helper(self) -> None:
        assert ma_cross_side(10, 11, 12, 11) == "buy"
        assert ma_cross_side(12, 11, 10, 11) == "sell"
        assert ma_cross_side(12, 11, 13, 11) is None
        assert rsi_reversion_side(20, 30, 70) == "buy"
        assert rsi_reversion_side(80, 30, 70) == "sell"
        assert rsi_reversion_side(50, 30, 70) is None


class TestNotesAndRationale:
    def test_note_crud(self, client: TestClient) -> None:
        empty = client.get("/api/v1/notes").json()
        assert empty == []
        created = client.post(
            "/api/v1/notes",
            json={"body": "Watch Tencent on policy", "market_id": "hk", "symbol": "0700.HK"},
        )
        assert created.status_code == 200
        note = created.json()
        assert note["body"] == "Watch Tencent on policy"
        listed = client.get("/api/v1/notes").json()
        assert len(listed) == 1
        bad = client.post("/api/v1/notes", json={"body": "   "})
        assert bad.status_code == 400
        deleted = client.delete(f"/api/v1/notes/{note['id']}")
        assert deleted.status_code == 200
        assert client.get("/api/v1/notes").json() == []
        assert client.delete("/api/v1/notes/999").status_code == 404
        too_long = client.post("/api/v1/notes", json={"body": "x" * 4001})
        assert too_long.status_code == 422

    def test_order_keeps_rationale(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/orders",
            json={
                "market": "us",
                "symbol": "AAPL",
                "side": "buy",
                "quantity": 5,
                "rationale": "SMA crossed above; RSI still neutral.",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["rationale"] == "SMA crossed above; RSI still neutral."
        orders = client.get("/api/v1/orders").json()
        assert orders[0]["rationale"] == body["rationale"]

    def test_blank_rationale_stored_as_null(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/orders",
            json={"market": "us", "symbol": "AAPL", "side": "buy", "quantity": 1, "rationale": "   "},
        )
        assert resp.status_code == 200
        assert resp.json()["rationale"] is None

    def test_adds_rationale_column_on_old_orders_table(self) -> None:
        from sqlalchemy import create_engine, inspect, text

        engine = create_engine("sqlite:///:memory:", future=True)
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE orders (id INTEGER PRIMARY KEY, status TEXT)"))
        _ensure_columns(engine)
        cols = {c["name"] for c in inspect(engine).get_columns("orders")}
        assert "rationale" in cols
