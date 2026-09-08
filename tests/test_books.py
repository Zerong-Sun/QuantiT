"""Paper book catalog: book_id vs venue, separate cash, shared symbols."""

from __future__ import annotations

from datetime import datetime

from quantit.markets.assets import asset_class, is_allowed
from quantit.markets.cn import CNAdapter
from quantit.markets.display import display_label
from quantit.markets.hk import HKAdapter
from quantit.markets.registry import MarketRegistry
from quantit.markets.us import USAdapter
from quantit.paper.books import DESK_BOOK_IDS, PAPER_BOOKS, PAPER_CASH, get_book, venue_of
from quantit.paper.broker import PaperBroker
from quantit.paper.db import create_session
from quantit.data.provider import DataProvider
import pandas as pd


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
    frames = {
        "JNJ": _ohlcv(start_price=150.0),
        "0700.HK": _ohlcv(start_price=300.0),
        "510300.SS": _ohlcv(start_price=3.5),
    }
    provider = FakeProvider(frames)
    registry = MarketRegistry()
    registry.register(USAdapter(provider=provider))
    registry.register(HKAdapter(provider=provider))
    registry.register(CNAdapter(provider=provider))
    return registry


def test_venue_of_maps_books_and_passes_venues() -> None:
    assert venue_of("us") == "us"
    assert venue_of("us_book") == "us"
    assert venue_of("hk_theme") == "hk"
    assert venue_of("cn_etf") == "cn"
    assert venue_of("cl") == "cl"
    assert venue_of("hk") == "hk"


def test_catalog_has_seven_books_and_desk_skips_cl() -> None:
    ids = [book.book_id for book in PAPER_BOOKS]
    assert ids == ["us", "us_book", "hk", "hk_theme", "cn", "cn_etf", "cl"]
    assert DESK_BOOK_IDS == ("us", "us_book", "hk", "hk_theme", "cn", "cn_etf")
    assert get_book("hk_theme") is not None
    assert get_book("hk_theme").strategy_id == "theme_rotation"
    assert PAPER_CASH["us_book"] == PAPER_CASH["us"] == 100_000.0
    assert PAPER_CASH["hk_theme"] == PAPER_CASH["hk"] == 1_000_000.0


def test_ensure_accounts_creates_new_books_keeps_existing_seeds() -> None:
    session = create_session("sqlite:///:memory:")
    broker = PaperBroker(session, registry=_registry(), now=lambda: datetime(2024, 6, 10, 10, 0, 0))
    broker.ensure_accounts()
    cash = {a.market_id: a.cash for a in broker.list_accounts()}
    assert set(cash) == {"us", "us_book", "hk", "hk_theme", "cn", "cn_etf"}
    assert cash["us"] == 100_000.0
    assert cash["us_book"] == 100_000.0
    assert cash["hk_theme"] == 1_000_000.0
    assert cash["cn_etf"] == 1_000_000.0
    us = broker.get_account("us")
    us.cash = 80_000.0
    broker.session.commit()
    broker.ensure_accounts()
    assert broker.get_account("us").cash == 80_000.0
    assert broker.get_account("us").initial_cash == 100_000.0
    assert broker.get_account("us_book").cash == 100_000.0


def test_two_us_books_can_hold_the_same_symbol() -> None:
    session = create_session("sqlite:///:memory:")
    broker = PaperBroker(session, registry=_registry(), now=lambda: datetime(2024, 6, 10, 10, 0, 0))
    broker.ensure_accounts()
    a = broker.place_order("us", "JNJ", "buy", 10)
    b = broker.place_order("us_book", "JNJ", "buy", 4)
    assert a.status == "filled"
    assert b.status == "filled"
    assert broker.get_position("us", "JNJ").quantity == 10
    assert broker.get_position("us_book", "JNJ").quantity == 4
    assert broker.get_account("us").cash < PAPER_CASH["us"]
    assert broker.get_account("us_book").cash < PAPER_CASH["us_book"]
    assert broker.get_account("us").cash != broker.get_account("us_book").cash


def test_hk_theme_order_fills_via_hk_adapter() -> None:
    session = create_session("sqlite:///:memory:")
    broker = PaperBroker(session, registry=_registry(), now=lambda: datetime(2024, 6, 10, 10, 0, 0))
    broker.ensure_accounts()
    order = broker.place_order("hk_theme", "0700.HK", "buy", 100)
    assert order.status == "filled"
    assert order.market_id == "hk_theme"
    assert broker.get_position("hk_theme", "0700.HK") is not None
    assert broker.get_position("hk", "0700.HK") is None


def test_asset_class_and_labels_follow_venue() -> None:
    assert asset_class("hk_theme", "0700.HK") == "equity"
    assert is_allowed("cn_etf", "510300.SS")
    assert display_label("hk_theme", "0700.HK") == "Tencent（0700.HK）"
    assert display_label("cn_etf", "510300.SS") == "CSI 300 ETF（510300.SS）"
    assert display_label("us_book", "JNJ") == "JNJ"
