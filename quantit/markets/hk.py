"""Hong Kong market profile and Hang Seng TECH / Chinese internet universe."""

from __future__ import annotations

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
