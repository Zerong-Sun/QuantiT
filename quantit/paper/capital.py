"""Paper account seed cash and tradable asset classes."""

from __future__ import annotations

from quantit.markets.assets import ALLOWED_ASSET_CLASSES

# Idle accounts are seeded (or rebased) to these notionals.
PAPER_CASH: dict[str, float] = {
    "us": 100_000.0,
    "hk": 1_000_000.0,
    "cn": 1_000_000.0,
}

US_WATCHLIST: tuple[str, ...] = ("AAPL", "MSFT", "NVDA", "SPY", "QQQ")
HK_ETF_WATCHLIST: tuple[str, ...] = ("2800.HK", "2828.HK", "3033.HK", "3067.HK")
# 5-digit 认购证；东财日线（Yahoo 通常无五位轮证）。偏恒生科技/恒指多头，且需有约一个月行情才能跑 MA/RSI。
HK_WARRANT_WATCHLIST: tuple[str, ...] = (
    "27882.HK",  # Macquarie Tencent call ~Dec 2026
    "13606.HK",  # JP Hang Seng Index call ~Dec 2026
    "14567.HK",  # Guojun SMIC call ~Apr 2027
)

# Fraction of *initial* US cash used for one new long (keeps ~5 slots in a $100k book).
US_SLOT_PCT: float = 0.20
# Extra sleeve for one ATM call overlay on the same name (premium * 100).
US_OPTION_SLOT_PCT: float = 0.05
# HK warrant / CBBC sleeve as a fraction of initial HKD cash.
HK_WARRANT_SLOT_PCT: float = 0.05

# Halt new US buys when mark-to-market equity is this far below initial cash.
PAPER_MAX_DRAWDOWN: float = 0.20
