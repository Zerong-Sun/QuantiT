"""US equities market profile and Yahoo-backed adapter."""

from __future__ import annotations

from quantit.markets.adapter import MarketAdapter
from quantit.markets.base import MarketProfile

US_PROFILE = MarketProfile(
    name="us",
    currency="USD",
    trading_days_per_year=252,
    commission_rate=0.0,
    stamp_duty_rate=0.0,
    slippage_rate=0.0005,
    lot_size_note="Odd lots are allowed.",
)

US_UNIVERSE: dict[str, str] = {
    "AAPL": "Apple",
    "MSFT": "Microsoft",
    "GOOGL": "Alphabet",
    "AMZN": "Amazon",
    "NVDA": "NVIDIA",
    "META": "Meta",
    "TSLA": "Tesla",
    "JPM": "JPMorgan",
    "SPY": "SPDR S&P 500",
    "QQQ": "Invesco QQQ",
    "IWM": "iShares Russell 2000",
    "DIA": "SPDR Dow Jones",
    "XLK": "Technology Select Sector",
    "GLD": "SPDR Gold Shares",
    "TLT": "iShares 20+ Year Treasury",
    "SOXX": "iShares Semiconductor",
}


class USAdapter(MarketAdapter):
    market_id = "us"
    profile = US_PROFILE
    timezone = "America/New_York"
    session_hours = "09:30-16:00 ET"
    t_plus = 0

    def normalize_symbol(self, raw: str) -> str:
        return raw.strip().upper()

    def lot_size(self, symbol: str) -> int:
        return 1

    def universe(self) -> dict[str, str]:
        return US_UNIVERSE
