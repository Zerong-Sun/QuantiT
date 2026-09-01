"""Hong Kong market profile and Hang Seng TECH / Chinese internet universe."""

from __future__ import annotations

from quantit.markets.adapter import MarketAdapter
from quantit.markets.base import MarketProfile

HK_PROFILE = MarketProfile(
    name="hk",
    currency="HKD",
    trading_days_per_year=247,
    commission_rate=0.0008,
    stamp_duty_rate=0.001,
    slippage_rate=0.0005,
    lot_size_note="HKEX board lots are not enforced in v1 backtests.",
)

# Yahoo Finance symbols. Theme rotation stays inside tech/internet, not finance/property.
HSTECH_THEMES: dict[str, list[str]] = {
    "platforms": [
        "0700.HK",  # Tencent
        "9988.HK",  # Alibaba
        "3690.HK",  # Meituan
        "9618.HK",  # JD.com
        "1024.HK",  # Kuaishou
        "9999.HK",  # NetEase
        "9888.HK",  # Baidu
    ],
    "hardware": [
        "1810.HK",  # Xiaomi
        "0992.HK",  # Lenovo
        "2382.HK",  # Sunny Optical
    ],
    "semis": [
        "0981.HK",  # SMIC
        "1347.HK",  # Hua Hong
    ],
    "ev": [
        "1211.HK",  # BYD
        "2015.HK",  # Li Auto
        "9866.HK",  # NIO
        "9868.HK",  # XPeng
    ],
}

THEME_NAMES: tuple[str, ...] = tuple(HSTECH_THEMES.keys())


def all_hstech_symbols() -> list[str]:
    """Flatten the core pool, preserving theme order and uniqueness."""
    seen: set[str] = set()
    out: list[str] = []
    for members in HSTECH_THEMES.values():
        for symbol in members:
            if symbol not in seen:
                seen.add(symbol)
                out.append(symbol)
    return out


def theme_of(symbol: str) -> str | None:
    """Return the theme name for a universe symbol, if any."""
    for name, members in HSTECH_THEMES.items():
        if symbol in members:
            return name
    return None


HK_NAMES: dict[str, str] = {
    "0700.HK": "Tencent",
    "9988.HK": "Alibaba",
    "3690.HK": "Meituan",
    "9618.HK": "JD.com",
    "1024.HK": "Kuaishou",
    "9999.HK": "NetEase",
    "9888.HK": "Baidu",
    "1810.HK": "Xiaomi",
    "0992.HK": "Lenovo",
    "2382.HK": "Sunny Optical",
    "0981.HK": "SMIC",
    "1347.HK": "Hua Hong",
    "1211.HK": "BYD",
    "2015.HK": "Li Auto",
    "9866.HK": "NIO",
    "9868.HK": "XPeng",
}

# Known board lots. Missing entries skip lot enforcement (see lot_size_note).
HK_BOARD_LOTS: dict[str, int] = {
    "0700.HK": 100,
    "9988.HK": 100,
    "1810.HK": 200,
}


class HKAdapter(MarketAdapter):
    market_id = "hk"
    profile = HK_PROFILE
    timezone = "Asia/Hong_Kong"
    session_hours = "09:30-16:00 HKT"
    t_plus = 0

    def normalize_symbol(self, raw: str) -> str:
        s = raw.strip().upper()
        if s.endswith(".HK"):
            s = s[: -len(".HK")]
        digits = s.lstrip("0") or "0"
        if digits.isdigit():
            return f"{int(digits):04d}.HK"
        return f"{s}.HK"

    def lot_size(self, symbol: str) -> int:
        return HK_BOARD_LOTS.get(self.normalize_symbol(symbol), 0)

    def universe(self) -> dict[str, str]:
        return HK_NAMES
