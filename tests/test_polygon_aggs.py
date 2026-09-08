"""Polygon daily aggregates (mocked HTTP, no live key required)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.request import Request

import pandas as pd
import pytest

from quantit.data.polygon_aggs import PolygonDailyProvider


class FakeResponse:
    def __init__(self, payload: object, status: int = 200) -> None:
        body = json.dumps(payload) if not isinstance(payload, (bytes, str)) else payload
        self._body = body.encode("utf-8") if isinstance(body, str) else body
        self.status = status

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None


def _ms(year: int, month: int, day: int) -> int:
    return int(datetime(year, month, day, 20, 0, tzinfo=timezone.utc).timestamp() * 1000)


def test_missing_api_key() -> None:
    with pytest.raises(ValueError, match="POLYGON_API_KEY"):
        PolygonDailyProvider(api_key="", min_interval_sec=0).fetch("JNJ", "2026-01-02", "2026-01-10")


def test_parses_adjusted_daily_bars() -> None:
    payload = {
        "status": "DELAYED",
        "resultsCount": 2,
        "results": [
            {"t": _ms(2026, 1, 2), "o": 160.0, "h": 162.0, "l": 159.0, "c": 161.0, "v": 1_000},
            {"t": _ms(2026, 1, 5), "o": 161.0, "h": 163.0, "l": 160.0, "c": 162.5, "v": 1_100},
        ],
    }

    def opener(request: Request, timeout: int = 20) -> FakeResponse:
        assert "JNJ" in request.full_url
        assert "adjusted=true" in request.full_url
        return FakeResponse(payload)

    provider = PolygonDailyProvider(api_key="test-key", min_interval_sec=0, opener=opener)
    df = provider.fetch("jnj", "2026-01-02", "2026-01-10")
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert len(df) == 2
    assert float(df["close"].iloc[-1]) == 162.5


def test_old_window_raises_before_http() -> None:
    called = []

    def opener(request: Request, timeout: int = 20) -> FakeResponse:
        called.append(request.full_url)
        return FakeResponse({"status": "OK", "results": []})

    provider = PolygonDailyProvider(api_key="test-key", min_interval_sec=0, opener=opener)
    with pytest.raises(ValueError, match="older than Polygon free window"):
        provider.fetch("JNJ", "2018-01-02", "2018-06-01")
    assert called == []


def test_not_authorized_raises() -> None:
    def opener(request: Request, timeout: int = 20) -> FakeResponse:
        return FakeResponse({"status": "NOT_AUTHORIZED", "message": "upgrade"})

    provider = PolygonDailyProvider(api_key="test-key", min_interval_sec=0, opener=opener)
    with pytest.raises(ValueError, match="upgrade"):
        provider.fetch("JNJ", "2026-01-02", "2026-01-10")
