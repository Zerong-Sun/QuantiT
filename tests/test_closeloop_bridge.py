"""Closeloop API bridge: fixture research vs dump-only ``cl`` orders."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from closeloop.data.ingest import ingest
from closeloop.loop.book import TargetBook
from closeloop.loop.worker import LoopWorker
from quantit.api.closeloop_bridge import apply_target_book
from quantit.data.provider import DataProvider
from quantit.markets.cl import CLAdapter
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


def _paper_registry() -> MarketRegistry:
    registry = MarketRegistry()
    registry.register(USAdapter(provider=FakeProvider({"AAPL": _ohlcv(start_price=100.0)})))
    registry.register(HKAdapter(provider=FakeProvider({"0700.HK": _ohlcv(start_price=300.0)})))
    registry.register(CNAdapter(provider=FakeProvider({"600519.SS": _ohlcv(start_price=10.0)})))
    return registry


def _dump(tmp_path, n: int = 40) -> tuple[MarketRegistry, object]:
    csv_dir = tmp_path / "csv"
    csv_dir.mkdir()
    dates = pd.bdate_range("2024-01-02", periods=n)
    for j, inst in enumerate(("SH600000", "SZ000001")):
        close = 10.0 + j + 0.02 * pd.RangeIndex(n)
        pd.DataFrame(
            {
                "date": dates,
                "open": close,
                "high": close + 0.3,
                "low": close - 0.3,
                "close": close,
                "volume": 1_000_000,
            }
        ).to_csv(csv_dir / f"{inst}.csv", index=False)
    dest = tmp_path / "qlib_cn"
    ingest(dest=dest, from_csv=csv_dir, add_cap=False)
    registry = _paper_registry()
    registry.register(CLAdapter(data_dir=dest))
    return registry, dest


def test_fixture_step_does_not_order_cl(tmp_path) -> None:
    from quantit.api.app import create_app

    registry = _paper_registry()
    session = create_session("sqlite:///:memory:")
    broker = PaperBroker(session, registry=registry, now=lambda: datetime(2024, 6, 10, 10, 0, 0))
    worker = LoopWorker(artifacts_dir=tmp_path, force_fixture=True)
    app = create_app(broker=broker, registry=registry, closeloop_worker=worker)
    client = TestClient(app)
    before = {a["market_id"]: a["cash"] for a in client.get("/api/v1/accounts").json()}
    body = client.post("/api/v1/closeloop/step").json()
    assert body["source"] == "fixture"
    assert body["can_trade"] is False
    assert body.get("fills") == []
    after = {a["market_id"]: a["cash"] for a in client.get("/api/v1/accounts").json()}
    assert after["us"] == pytest.approx(before["us"])
    assert after["hk"] == pytest.approx(before["hk"])
    assert after["cn"] == pytest.approx(before["cn"])
    assert body["last_alpha"] is not None
    lib = client.get("/api/v1/closeloop/library").json()
    assert isinstance(lib, list)
    status = client.get("/api/v1/closeloop/status").json()
    assert "cl_equity" in status
    assert status["cl_currency"] == "CNY"
    stopped = client.post("/api/v1/closeloop/stop").json()
    assert stopped["running"] is False


def test_apply_target_book_only_touches_cl(tmp_path) -> None:
    registry, _dest = _dump(tmp_path)
    session = create_session("sqlite:///:memory:")
    broker = PaperBroker(session, registry=registry, now=lambda: datetime(2024, 6, 10, 10, 0, 0))
    broker.ensure_accounts()
    us_cash = broker.get_account("us").cash
    hk_cash = broker.get_account("hk").cash
    cn_cash = broker.get_account("cn").cash
    book = TargetBook(weights={"SH600000": 1.0}, alpha_id="006", rationale="test cl")
    fills = apply_target_book(broker, book)
    assert fills
    assert all(f["status"] in {"filled", "rejected"} for f in fills)
    assert broker.get_account("us").cash == pytest.approx(us_cash)
    assert broker.get_account("hk").cash == pytest.approx(hk_cash)
    assert broker.get_account("cn").cash == pytest.approx(cn_cash)
    pos = broker.get_position("cl", "SH600000")
    assert pos is not None and pos.quantity >= 100
    assert broker.get_account("cl").cash < 1_000_000.0
    first_qty = pos.quantity
    again = apply_target_book(broker, book)
    assert broker.get_position("cl", "SH600000").quantity == first_qty
    assert all(f["side"] != "buy" or f["status"] == "rejected" for f in again)


def test_sidecar_empty_inbox_does_not_rotate(tmp_path) -> None:
    from quantit.api.app import create_app

    registry = _paper_registry()
    session = create_session("sqlite:///:memory:")
    broker = PaperBroker(session, registry=registry, now=lambda: datetime(2024, 6, 10, 10, 0, 0))
    worker = LoopWorker(artifacts_dir=tmp_path, force_fixture=True)
    app = create_app(broker=broker, registry=registry, closeloop_worker=worker)
    client = TestClient(app)
    body = client.post("/api/v1/closeloop/sidecar").json()
    assert body["processed"] == 0
    assert body.get("last_alpha") is None


def test_dump_step_can_trade_when_gates_pass(tmp_path, monkeypatch) -> None:
    from quantit.api.app import create_app
    from closeloop.loop.book import TargetBook
    from closeloop.validate.gates import GateReport

    registry, dest = _dump(tmp_path)
    session = create_session("sqlite:///:memory:")
    broker = PaperBroker(session, registry=registry, now=lambda: datetime(2024, 6, 10, 10, 0, 0))
    worker = LoopWorker(artifacts_dir=tmp_path / "art", data_dir=dest, force_fixture=False)
    fake = GateReport(True, 0.05, 1.0, 0.02, 0.1, [])
    monkeypatch.setattr("closeloop.loop.worker.evaluate_spec", lambda *a, **k: fake)
    monkeypatch.setattr(
        "closeloop.loop.worker.target_book_from_factor",
        lambda *a, **k: TargetBook(weights={"SH600000": 1.0}, alpha_id="006", rationale="mock"),
    )
    app = create_app(broker=broker, registry=registry, closeloop_worker=worker)
    client = TestClient(app)
    us_before = broker.get_account("us").cash
    body = client.post("/api/v1/closeloop/step").json()
    assert body.get("last_error") in (None, "")
    assert body["source"] == "qlib_dump"
    assert body["can_trade"] is True
    assert "cl_equity" in body
    assert broker.get_account("us").cash == pytest.approx(us_before)
    assert body.get("fills")
    assert broker.get_position("cl", "SH600000") is not None
