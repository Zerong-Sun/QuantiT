"""Research universes selected by four quality criteria (not Nasdaq-by-default).

A good company here means: healthy end-market, stable management system,
complete production/R&D (or equivalent operating network), and the ability
to self-correct across a cycle. These lists pick the training pool only.
TSMOM still trades price; it does not score these labels.

Berkshire is a philosophical reference, not a 13F clone. Japan is out of
scope until a JP market adapter exists.
"""

from __future__ import annotations

# US quality — main research book.
# JNJ/PG/KO: durable demand + operating systems that have survived cycles.
# UNH: healthcare operations (clinical/admin network).
# HON/CAT: industrial production and R&D.
# WMT: retail operating system that reinvented logistics.
# CVX: real energy production (not a theme ETF).
# AXP: payments network / underwriting franchise.
# AAPL (optional extra): product stack that has reinvented itself; not NVDA/QQQ.
US_QUALITY: tuple[str, ...] = (
    "JNJ",
    "PG",
    "KO",
    "UNH",
    "HON",
    "CAT",
    "WMT",
    "CVX",
    "AXP",
)

US_QUALITY_EVOLUTION_EXTRA: tuple[str, ...] = ("AAPL",)

US_NASDAQ_CONTRAST: tuple[str, ...] = ("AAPL", "MSFT", "NVDA", "SPY", "QQQ")

# Equal-weight BH is the pool itself; BRK.B is printed as a reference only.
US_QUALITY_BENCHMARK: str = "BRK.B"
YAHOO_ALIASES: dict[str, str] = {"BRK.B": "BRK-B", "BRK.A": "BRK-A"}

# HK operating blue chips — not Hang Seng TECH rotation.
# 0002.HK CLP: grid operations, stable demand.
# 0941.HK China Mobile: network operations.
# 0005.HK HSBC: institutional management (cycle-tested).
# 1299.HK AIA: insurance operations.
# 0388.HK HKEX: market infrastructure.
# 0001.HK CK Hutchison: diversified operating businesses.
# 0669.HK Techtronic: manufacturing + R&D.
HK_QUALITY: tuple[str, ...] = (
    "0002.HK",
    "0941.HK",
    "0005.HK",
    "1299.HK",
    "0388.HK",
    "0001.HK",
    "0669.HK",
)

# CN operating quality — not industry-ETF themes.
# 000333.SZ Midea: manufacturing + R&D.
# 600276.SS Hengrui: pharma R&D.
# 600900.SS Yangtze Power: generation operations.
# 600036.SS CMB: bank franchise / risk systems.
# 601318.SS Ping An: insurance + operating platforms.
# 600519.SS Moutai: durable consumer franchise.
CN_QUALITY: tuple[str, ...] = (
    "000333.SZ",
    "600276.SS",
    "600900.SS",
    "600036.SS",
    "601318.SS",
    "600519.SS",
)

CN_QUALITY_MARKET: str = "510300.SS"


def default_research_symbols() -> list[str]:
    """CLI default: US quality book, not the paper Nasdaq watchlist."""
    return list(US_QUALITY)


def promote_universe(strategy_id: str) -> tuple[str, ...] | None:
    """Paper watchlist that --promote is allowed to write. Nasdaq contrast is None."""
    mapping: dict[str, tuple[str, ...]] = {
        "tsmom": US_QUALITY,
        "hk_quality_book": HK_QUALITY,
        "cn_quality_book": CN_QUALITY,
    }
    return mapping.get(strategy_id)


def traded_universe(strategy_id: str, names: list[str] | None) -> list[str]:
    """Symbols the study actually trades. Quality books ignore a leftover US default."""
    requested = [str(s).strip() for s in (names or []) if s and str(s).strip()]
    default_us = {s.upper() for s in US_QUALITY}
    if strategy_id == "hk_quality_book":
        if requested and {s.upper() for s in requested} != default_us:
            return requested
        return list(HK_QUALITY)
    if strategy_id == "cn_quality_book":
        if requested and {s.upper() for s in requested} != default_us:
            return requested
        return list(CN_QUALITY)
    return requested or list(US_QUALITY)


def universe_allows_promote(strategy_id: str, symbols: list[str] | None) -> bool:
    """True when symbols match the paper quality pool (or were omitted = CLI default)."""
    allowed = promote_universe(strategy_id)
    if allowed is None:
        return False
    if symbols is None:
        return True
    have = {s.strip().upper() for s in symbols if s and str(s).strip()}
    if not have:
        return False
    return have == {s.upper() for s in allowed}
