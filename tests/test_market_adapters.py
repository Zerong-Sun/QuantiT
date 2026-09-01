"""Tests for pluggable market adapters (no network)."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest

from quantit.data.provider import DataProvider
from quantit.markets.cn import CN_PROFILE, CNAdapter
from quantit.markets.hk import HK_PROFILE, HKAdapter
from quantit.markets.registry import MarketRegistry, get_registry
from quantit.markets.us import US_PROFILE, USAdapter


def _ohlcv(n: int = 5, start: str = "2024-01-02", start_price: float = 100.0) -> pd.DataFrame:
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
        self.calls: list[tuple[str, str]] = []

    def fetch(self, symbol, start, end, interval: str = "1d") -> pd.DataFrame:
        self.calls.append((symbol, interval))
        if symbol not in self.frames:
            raise ValueError(f"No data returned for {symbol}")
        return self.frames[symbol].copy()


class TestSymbolNormalize:
    def test_us_uppercases_bare_ticker(self) -> None:
        assert USAdapter().normalize_symbol("aapl") == "AAPL"

    def test_hk_pads_and_suffixes(self) -> None:
        adapter = HKAdapter()
        assert adapter.normalize_symbol("700") == "0700.HK"
        assert adapter.normalize_symbol("0700.hk") == "0700.HK"
        assert adapter.normalize_symbol("9988.HK") == "9988.HK"

    def test_cn_maps_exchange_suffix(self) -> None:
        adapter = CNAdapter()
        assert adapter.normalize_symbol("600519") == "600519.SS"
        assert adapter.normalize_symbol("000001") == "000001.SZ"
        assert adapter.normalize_symbol("300750.sz") == "300750.SZ"


class TestProfiles:
    def test_us_profile(self) -> None:
        assert US_PROFILE.name == "us"
        assert US_PROFILE.currency == "USD"
        assert US_PROFILE.trading_days_per_year == 252

    def test_cn_profile_includes_t_plus_costs(self) -> None:
        assert CN_PROFILE.name == "cn"
        assert CN_PROFILE.currency == "CNY"
        assert CN_PROFILE.stamp_duty_rate == 0.0005
        assert CNAdapter().t_plus == 1
        assert USAdapter().t_plus == 0
        assert HKAdapter().t_plus == 0


class TestLotSizeAndQuantity:
    def test_us_allows_odd_lots(self) -> None:
        adapter = USAdapter()
        assert adapter.lot_size("AAPL") == 1
        assert adapter.validate_quantity("AAPL", 7) == []

    def test_cn_requires_board_lot_of_100(self) -> None:
        adapter = CNAdapter()
        assert adapter.lot_size("600519.SS") == 100
        errors = adapter.validate_quantity("600519.SS", 150)
        assert errors
        assert adapter.validate_quantity("600519.SS", 200) == []

    def test_hk_skips_enforcement_when_lot_unknown(self) -> None:
        adapter = HKAdapter()
        assert adapter.lot_size("9999.HK") == 0
        assert adapter.validate_quantity("9999.HK", 1) == []

    def test_hk_enforces_known_lot(self) -> None:
        adapter = HKAdapter()
        assert adapter.lot_size("0700.HK") == 100
        assert adapter.validate_quantity("0700.HK", 50)
        assert adapter.validate_quantity("0700.HK", 100) == []


class TestBarsAndQuote:
    def test_fetch_bars_uses_normalized_symbol(self) -> None:
        provider = FakeProvider({"AAPL": _ohlcv()})
        adapter = USAdapter(provider=provider)
        df = adapter.fetch_bars("aapl", "1d", "2024-01-01", "2024-01-10")
        assert list(df.columns) == ["open", "high", "low", "close", "volume"]
        assert provider.calls[0][0] == "AAPL"

    def test_fetch_quote_from_last_two_closes(self) -> None:
        df = _ohlcv(n=3, start_price=10.0)
        adapter = USAdapter(provider=FakeProvider({"MSFT": df}))
        quote = adapter.fetch_quote("MSFT")
        assert quote.symbol == "MSFT"
        assert quote.market_id == "us"
        assert quote.last == pytest.approx(12.0)
        assert quote.prev_close == pytest.approx(11.0)
        assert quote.change == pytest.approx(1.0)
        assert quote.delayed is True

    def test_cn_fetch_bars_passes_canonical_symbol(self) -> None:
        provider = FakeProvider({"600519.SS": _ohlcv()})
        adapter = CNAdapter(provider=provider)
        adapter.fetch_bars("600519", "1d", "2024-01-01", "2024-01-10")
        assert provider.calls[0][0] == "600519.SS"


class TestSearchAndInstrument:
    def test_us_search_matches_universe_and_exact(self) -> None:
        adapter = USAdapter()
        hits = adapter.search("aap")
        assert any(i.symbol == "AAPL" for i in hits)
        exact = adapter.search("XYZ")
        assert exact[0].symbol == "XYZ"
        assert exact[0].market_id == "us"

    def test_instrument_exposes_session(self) -> None:
        inst = USAdapter().instrument("AAPL")
        assert inst.timezone == "America/New_York"
        assert inst.currency == "USD"
        assert inst.lot_size == 1
        assert "09:30" in inst.session_hours


class TestRegistry:
    def test_register_and_get(self) -> None:
        registry = MarketRegistry()
        registry.register(USAdapter())
        assert registry.get("us").market_id == "us"
        with pytest.raises(KeyError):
            registry.get("jp")

    def test_default_registry_has_three_markets(self) -> None:
        registry = get_registry()
        assert set(registry.ids()) == {"us", "hk", "cn"}
        assert registry.get("hk").profile is HK_PROFILE
        assert registry.get("cn").profile is CN_PROFILE
