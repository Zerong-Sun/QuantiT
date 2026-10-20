from datetime import datetime
import json
import threading

import pandas as pd
import pytest

from quantit.markets.us import USAdapter
from quantit.paper.broker import PaperBroker
from quantit.paper.db import create_session
from quantit.paper.models import RecoveryDay
from quantit.paper.recovery import HistoricalAdapter, copy_database, replay
from quantit.paper.runner import PaperRunner
from tests.test_runner import _ohlcv, _registry


def test_historical_quotes_and_signals_never_see_future():
    frame = _ohlcv(n=5)
    day = frame.index[2]
    adapter = HistoricalAdapter(USAdapter(), {"AAPL": frame}, day)
    assert adapter.fetch_quote("AAPL").last == frame.iloc[2]["close"]
    assert adapter.fetch_bars("AAPL", "1d", "2020-01-01", "2030-01-01").index.max() == day
    adapter.day = pd.Timestamp("2024-01-07")  # Sunday: no invented session.
    with pytest.raises(ValueError, match="exact-session"):
        adapter.fetch_quote("AAPL")


def test_marks_survive_runner_restart(tmp_path):
    url = f"sqlite:///{tmp_path/'paper.db'}"
    broker = PaperBroker(create_session(url), _registry(), now=lambda: datetime(2024, 6, 10))
    PaperRunner(broker)._mark("us", "AAPL")
    broker.session.close()
    restarted = PaperBroker(create_session(url), _registry(), now=lambda: datetime(2024, 6, 10))
    assert PaperRunner(restarted)._already("us", "AAPL")
    assert not PaperRunner(restarted)._already("us_book", "AAPL")


def test_books_run_concurrently_and_errors_do_not_block_other_books(monkeypatch):
    broker = PaperBroker(create_session("sqlite:///:memory:"), _registry())
    broker.ensure_accounts()
    runner = PaperRunner(broker)
    barrier = threading.Barrier(2)
    def fail(force=False):
        barrier.wait(timeout=3)
        raise ValueError("US feed unavailable")
    def succeed(force=False):
        barrier.wait(timeout=3)
        return [{"market_id": "cn"}]
    monkeypatch.setattr(runner, "_tick_us", fail)
    monkeypatch.setattr(runner, "_tick_cn_quality", succeed)
    assert runner.tick(markets=("us", "cn")) == [{"market_id": "cn"}]
    assert runner.book_status["cn"]["state"] == "evaluated"
    assert "US feed unavailable" in runner.last_error
    with pytest.raises(ValueError, match="Unknown"):
        runner.tick(markets=("typo",))


@pytest.mark.parametrize("price", [float("nan"), float("inf"), -1, 0])
def test_invalid_quotes_cannot_corrupt_cash(price):
    frame = _ohlcv(n=3)
    frame["close"] = price
    broker = PaperBroker(create_session("sqlite:///:memory:"), _registry({"AAPL": frame}))
    broker.ensure_accounts()
    before = broker.get_account("us").cash
    assert broker.place_order("us", "AAPL", "buy", 1).status == "rejected"
    assert broker.get_account("us").cash == before


def test_stale_quote_rejected():
    broker = PaperBroker(
        create_session("sqlite:///:memory:"), _registry(),
        now=lambda: datetime(2026, 10, 20), max_quote_age_days=7,
    )
    broker.ensure_accounts()
    order = broker.place_order("us", "AAPL", "buy", 1)
    assert order.status == "rejected"
    assert "stale" in order.reject_reason


def test_replay_no_trade_days_are_durable_and_idempotent(tmp_path, monkeypatch):
    from quantit.paper import recovery
    frame = _ohlcv(n=5)
    frame.to_parquet(tmp_path/"bars.parquet")
    (tmp_path/"manifest.json").write_text(json.dumps({
        "AAPL": {"file": "bars.parquet"}, "SPY": {"file": "bars.parquet"},
        "DX-Y.NYB": {"file": "bars.parquet"},
    }))
    monkeypatch.setitem(recovery.BOOK_SYMBOLS, "us", ("AAPL",))
    monkeypatch.setattr(PaperRunner, "_tick_us", lambda *a, **k: [])
    broker = PaperBroker(create_session("sqlite:///:memory:"), _registry())
    broker.ensure_accounts()
    first = replay(broker, tmp_path, "2024-01-02", "2024-01-08", books=("us",))
    assert len(first) == 5
    assert all(r["status"] == "complete" for r in first)
    assert broker.session.query(RecoveryDay).count() == 5
    assert replay(broker, tmp_path, "2024-01-02", "2024-01-08", books=("us",)) == []
    assert broker.list_trades() == []


def test_copy_never_overwrites_source_or_existing_destination(tmp_path):
    source = tmp_path/"source.db"
    with pytest.raises(ValueError):
        copy_database(source, source)
    destination = tmp_path/"existing.db"
    destination.write_bytes(b"keep")
    with pytest.raises(ValueError):
        copy_database(source, destination)
    assert destination.read_bytes() == b"keep"


def test_blocked_recovery_is_not_skipped_after_partial_fills(tmp_path, monkeypatch):
    from quantit.paper import recovery
    frame = _ohlcv(n=5)
    frame.to_parquet(tmp_path/"bars.parquet")
    (tmp_path/"manifest.json").write_text(json.dumps({
        "AAPL": {"file": "bars.parquet"}, "SPY": {"file": "bars.parquet"},
        "DX-Y.NYB": {"file": "bars.parquet"},
    }))
    broker = PaperBroker(create_session("sqlite:///:memory:"), _registry(), now=lambda: datetime(2024, 1, 2))
    broker.ensure_accounts()
    broker.place_order("us", "AAPL", "buy", 1)
    broker.session.add(RecoveryDay(market_id="us", day="2024-01-02", status="blocked", detail="interrupted"))
    broker.session.commit()
    monkeypatch.setattr(PaperRunner, "_tick_us", lambda *a, **k: pytest.fail("must not bypass partial day"))
    results = recovery.replay(broker, tmp_path, "2024-01-02", "2024-01-08", books=("us",))
    assert results[0]["status"] == "blocked"
    assert len(results) == 1
    assert len(broker.list_orders()) == 1
    runner = PaperRunner(broker)
    assert runner.tick(markets=("us",)) == []
    assert runner.book_status["us"]["state"] == "blocked"


def test_session_close_uses_venue_timezone_and_dst():
    from quantit.paper.recovery import session_close
    assert session_close(pd.Timestamp("2026-10-20"), "cn") == datetime(2026, 10, 20, 7, 5)
    assert session_close(pd.Timestamp("2026-10-19"), "us") == datetime(2026, 10, 19, 20, 5)
    assert session_close(pd.Timestamp("2026-12-01"), "us") == datetime(2026, 12, 1, 21, 5)


def test_signal_api_requests_enough_calendar_history(monkeypatch):
    from fastapi.testclient import TestClient
    from quantit.api.app import create_app
    registry = _registry()
    broker = PaperBroker(create_session("sqlite:///:memory:"), registry)
    requests = []
    adapter = registry.get("us")
    original = adapter.fetch_bars
    def capture(symbol, interval, start, end):
        requests.append((pd.Timestamp(end)-pd.Timestamp(start)).days)
        return original(symbol, interval, start, end)
    monkeypatch.setattr(adapter, "fetch_bars", capture)
    client = TestClient(create_app(broker=broker, registry=registry))
    assert client.get("/api/v1/signals?market=us&symbol=AAPL").status_code == 200
    assert requests == [600]


def test_daily_adapter_excludes_unfinished_local_session(monkeypatch):
    import quantit.markets.adapter as module
    class Clock:
        @staticmethod
        def now(zone):
            return datetime(2024, 6, 10, 10, 0, tzinfo=zone)
    monkeypatch.setattr(module, "datetime", Clock)
    registry = _registry({"AAPL": _ohlcv(n=5, start="2024-06-06")})
    bars = registry.get("us").fetch_bars("AAPL", "1d", "2024-06-01", "2024-06-20")
    assert bars.index.max() == pd.Timestamp("2024-06-07")


def test_cn_fallback_accepts_timezone_aware_api_dates(monkeypatch):
    import sys
    from types import SimpleNamespace
    from quantit.markets.cn import TencentCNProvider
    raw = _ohlcv(n=3, start="2024-06-06").reset_index()
    raw = raw.rename(columns={raw.columns[0]: "date"})
    monkeypatch.setitem(sys.modules, "akshare", SimpleNamespace(stock_zh_a_hist_tx=lambda **kw: raw))
    bars = TencentCNProvider().fetch(
        "159995.SZ", pd.Timestamp("2024-06-06", tz="UTC"), pd.Timestamp("2024-06-07", tz="UTC"),
    )
    assert list(bars.index) == [pd.Timestamp("2024-06-06"), pd.Timestamp("2024-06-07")]
