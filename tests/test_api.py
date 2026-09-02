"""API tests for the paper terminal (no network)."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from quantit.data.provider import DataProvider
from quantit.markets.cn import CNAdapter
from quantit.markets.hk import HKAdapter
from quantit.markets.registry import MarketRegistry
from quantit.markets.us import USAdapter
from quantit.paper.broker import PaperBroker
from quantit.paper.db import create_session


def _ohlcv(n: int = 3, start: str = "2024-06-03", start_price: float = 100.0) -> pd.DataFrame:
    dates = pd.date_range(start, periods=n, freq="B")
    prices = [start_price + i for i in range(n)]
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


def _registry() -> MarketRegistry:
    registry = MarketRegistry()
    registry.register(USAdapter(provider=FakeProvider({"AAPL": _ohlcv(start_price=100.0)})))
    registry.register(HKAdapter(provider=FakeProvider({"0700.HK": _ohlcv(start_price=300.0)})))
    registry.register(CNAdapter(provider=FakeProvider({"600519.SS": _ohlcv(start_price=10.0)})))
    return registry


@pytest.fixture
def client() -> TestClient:
    from quantit.api.app import create_app

    registry = _registry()
    session = create_session("sqlite:///:memory:")
    broker = PaperBroker(session, registry=registry, now=lambda: datetime(2024, 6, 10, 10, 0, 0))
    app = create_app(broker=broker, registry=registry)
    return TestClient(app)


class TestMarketRoutes:
    def test_lists_registered_markets(self, client: TestClient) -> None:
        data = client.get("/api/v1/markets").json()
        ids = {m["id"] for m in data}
        assert ids == {"us", "hk", "cn"}
        us = next(m for m in data if m["id"] == "us")
        assert us["currency"] == "USD"
        assert us["timezone"] == "America/New_York"

    def test_search_and_instrument(self, client: TestClient) -> None:
        hits = client.get("/api/v1/search", params={"market": "us", "q": "aap"}).json()
        assert any(h["symbol"] == "AAPL" for h in hits)
        inst = client.get("/api/v1/instrument", params={"market": "us", "symbol": "aapl"}).json()
        assert inst["symbol"] == "AAPL"
        assert inst["lot_size"] == 1

    def test_bars_and_quote(self, client: TestClient) -> None:
        bars = client.get(
            "/api/v1/bars",
            params={
                "market": "us",
                "symbol": "AAPL",
                "interval": "1d",
                "start": "2024-06-01",
                "end": "2024-06-10",
            },
        ).json()
        assert len(bars) == 3
        assert {"time", "open", "high", "low", "close", "volume"} <= set(bars[0])
        quote = client.get("/api/v1/quote", params={"market": "us", "symbol": "AAPL"}).json()
        assert quote["last"] == pytest.approx(102.0)
        assert quote["delayed"] is True


class TestTradingRoutes:
    def test_accounts_seeded(self, client: TestClient) -> None:
        accounts = client.get("/api/v1/accounts").json()
        assert {a["market_id"] for a in accounts} == {"us", "hk", "cn"}
        by_id = {a["market_id"]: a for a in accounts}
        assert by_id["us"]["cash"] == pytest.approx(100_000)
        assert by_id["hk"]["cash"] == pytest.approx(1_000_000)
        assert by_id["cn"]["cash"] == pytest.approx(1_000_000)

    def test_place_order_and_blotter(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/orders",
            json={"market": "us", "symbol": "AAPL", "side": "buy", "quantity": 10},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "filled"
        positions = client.get("/api/v1/positions").json()
        assert positions[0]["symbol"] == "AAPL"
        assert positions[0]["quantity"] == 10
        trades = client.get("/api/v1/trades").json()
        assert len(trades) == 1
        orders = client.get("/api/v1/orders").json()
        assert orders[0]["id"] == body["id"]

    def test_unknown_market_404(self, client: TestClient) -> None:
        resp = client.get("/api/v1/quote", params={"market": "jp", "symbol": "7203"})
        assert resp.status_code == 404

    def test_health(self, client: TestClient) -> None:
        assert client.get("/api/health").json() == {"status": "ok"}

    def test_ui_is_served_at_root(self, client: TestClient) -> None:
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")
        assert b"QuantiT" in resp.content
