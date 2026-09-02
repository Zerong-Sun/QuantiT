"""Paper portfolio overview: mark-to-market value and period P&L."""

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
from quantit.paper.models import Position, Trade


def _ohlcv(n: int = 3, start: str = "2024-06-03", start_price: float = 100.0, step: float = 1.0) -> pd.DataFrame:
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


class BoomProvider(FakeProvider):
    def fetch(self, symbol, start, end, interval: str = "1d") -> pd.DataFrame:
        raise RuntimeError("feed down")


def _registry(frames: dict[str, dict[str, pd.DataFrame]] | None = None) -> MarketRegistry:
    frames = frames or {}
    us = frames.get("us", {"AAPL": _ohlcv(start_price=100.0)})
    hk = frames.get("hk", {"0700.HK": _ohlcv(start_price=300.0)})
    cn = frames.get("cn", {"600519.SS": _ohlcv(start_price=10.0)})
    registry = MarketRegistry()
    registry.register(USAdapter(provider=FakeProvider(us)))
    registry.register(HKAdapter(provider=FakeProvider(hk)))
    registry.register(CNAdapter(provider=FakeProvider(cn)))
    return registry


def _client(now: datetime | None = None, registry: MarketRegistry | None = None) -> TestClient:
    from quantit.api.app import create_app

    registry = registry or _registry()
    session = create_session("sqlite:///:memory:")
    broker = PaperBroker(
        session,
        registry=registry,
        now=lambda: now or datetime(2024, 6, 10, 10, 0, 0),
    )
    app = create_app(broker=broker, registry=registry)
    return TestClient(app)


@pytest.fixture
def client() -> TestClient:
    return _client()


class TestPortfolioRoute:
    def test_empty_books(self, client: TestClient) -> None:
        data = client.get("/api/v1/portfolio").json()
        by_id = {b["market_id"]: b for b in data["books"]}
        assert by_id["us"]["invested"] == pytest.approx(0.0)
        assert by_id["us"]["equity"] == pytest.approx(100_000.0)
        assert by_id["us"]["day_pnl"] == pytest.approx(0.0)
        assert data["positions"] == []

    def test_marks_open_position(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/orders",
            json={"market": "us", "symbol": "AAPL", "side": "buy", "quantity": 10},
        )
        assert resp.status_code == 200
        data = client.get("/api/v1/portfolio").json()
        us = next(b for b in data["books"] if b["market_id"] == "us")
        pos = data["positions"][0]
        assert pos["symbol"] == "AAPL"
        assert pos["market_value"] == pytest.approx(10 * 102.0)
        assert us["invested"] == pytest.approx(1020.0)
        assert us["equity"] < us["initial_cash"]
        assert pos["weight"] == pytest.approx(1.0)
        assert pos["day_pnl"] == pytest.approx(10.0)
        assert pos["unrealized"] is not None

    def test_month_pnl_keeps_older_fills(self, client: TestClient) -> None:
        client.post(
            "/api/v1/orders",
            json={"market": "us", "symbol": "AAPL", "side": "buy", "quantity": 10},
        )
        broker = client.app.state.broker
        trade = broker.session.query(Trade).one()
        trade.timestamp = datetime(2024, 5, 15, 10, 0, 0)
        broker.session.commit()

        data = client.get("/api/v1/portfolio").json()
        us = next(b for b in data["books"] if b["market_id"] == "us")
        assert us["month_pnl"] == pytest.approx(20.0)
        assert us["day_pnl"] == pytest.approx(10.0)
        assert us["week_pnl"] == pytest.approx(10.0)

    def test_week_pnl_excludes_week_start_bar(self) -> None:
        frames = {
            "us": {
                "AAPL": _ohlcv(n=4, start="2024-06-07", start_price=100.0),
            }
        }
        # Fri 7=100, Mon 10=101, Tue 11=102, Wed 12=103
        client = _client(now=datetime(2024, 6, 12, 18, 0, 0), registry=_registry(frames))
        client.post(
            "/api/v1/orders",
            json={"market": "us", "symbol": "AAPL", "side": "buy", "quantity": 10},
        )
        broker = client.app.state.broker
        trade = broker.session.query(Trade).one()
        trade.timestamp = datetime(2024, 5, 15, 10, 0, 0)
        broker.session.commit()

        data = client.get("/api/v1/portfolio").json()
        us = next(b for b in data["books"] if b["market_id"] == "us")
        pos = data["positions"][0]
        assert pos["last"] == pytest.approx(103.0)
        assert pos["day_pnl"] == pytest.approx(10.0)
        # Week starts Monday 10th; mark at Friday close 100, not Monday 101.
        assert us["week_pnl"] == pytest.approx(30.0)
        assert us["day_pnl"] == pytest.approx(10.0)

    def test_two_names_weights_sum_to_one(self) -> None:
        frames = {
            "us": {
                "AAPL": _ohlcv(start_price=100.0),
                "MSFT": _ohlcv(start_price=200.0),
            }
        }
        client = _client(registry=_registry(frames))
        client.post("/api/v1/orders", json={"market": "us", "symbol": "AAPL", "side": "buy", "quantity": 10})
        client.post("/api/v1/orders", json={"market": "us", "symbol": "MSFT", "side": "buy", "quantity": 10})
        data = client.get("/api/v1/portfolio").json()
        us_pos = [p for p in data["positions"] if p["market_id"] == "us"]
        assert len(us_pos) == 2
        assert sum(p["weight"] for p in us_pos) == pytest.approx(1.0)
        invested = next(b for b in data["books"] if b["market_id"] == "us")["invested"]
        assert invested == pytest.approx(10 * 102 + 10 * 202)

    def test_round_trip_leaves_no_position(self, client: TestClient) -> None:
        client.post("/api/v1/orders", json={"market": "us", "symbol": "AAPL", "side": "buy", "quantity": 10})
        client.post("/api/v1/orders", json={"market": "us", "symbol": "AAPL", "side": "sell", "quantity": 10})
        data = client.get("/api/v1/portfolio").json()
        us = next(b for b in data["books"] if b["market_id"] == "us")
        assert data["positions"] == []
        assert us["invested"] == pytest.approx(0.0)
        assert us["day_pnl"] < 0
        assert us["equity"] < us["initial_cash"]

    def test_broken_feed_does_not_500(self) -> None:
        registry = MarketRegistry()
        registry.register(USAdapter(provider=BoomProvider({})))
        client = _client(registry=registry)
        broker = client.app.state.broker
        account = broker.get_account("us")
        broker.session.add(
            Position(account_id=account.id, market_id="us", symbol="AAPL", quantity=8, avg_cost=100.0)
        )
        broker.session.commit()
        resp = client.get("/api/v1/portfolio")
        assert resp.status_code == 200
        data = resp.json()
        pos = data["positions"][0]
        assert pos["last"] == pytest.approx(100.0)
        assert pos["unrealized"] == pytest.approx(0.0)
        assert pos["market_value"] == pytest.approx(800.0)
        us = next(b for b in data["books"] if b["market_id"] == "us")
        assert us["invested"] == pytest.approx(800.0)

    def test_portfolio_page_is_served(self, client: TestClient) -> None:
        resp = client.get("/portfolio")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")
