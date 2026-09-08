"""Classify paper-tradable symbols (equity / ETF / option / warrant)."""

from __future__ import annotations

import re

# What the paper book is allowed to trade, including auto overlay for
# US listed calls and HK 5-digit warrants / CBBCs. Keys are venues, not book ids.
ALLOWED_ASSET_CLASSES: dict[str, frozenset[str]] = {
    "us": frozenset({"equity", "etf", "option"}),
    "hk": frozenset({"equity", "etf", "warrant"}),
    "cn": frozenset({"equity", "etf"}),
    "cl": frozenset({"equity"}),
}

# Yahoo OCC-style listed options: AAPL250117C00150000
_US_OPTION = re.compile(r"^([A-Z]{1,6})\d{6}[CP]\d{8}$")

US_ETFS: frozenset[str] = frozenset(
    {
        "SPY",
        "QQQ",
        "IWM",
        "DIA",
        "VTI",
        "VOO",
        "XLK",
        "XLF",
        "XLE",
        "GLD",
        "TLT",
        "HYG",
        "SOXX",
        "ARKK",
        "EEM",
        "KWEB",
    }
)

HK_ETFS: dict[str, str] = {
    "2800.HK": "Tracker Fund of Hong Kong",
    "2828.HK": "Hang Seng H-Share ETF",
    "2822.HK": "CSOP FTSE China A50 ETF",
    "3033.HK": "CSOP Hang Seng TECH ETF",
    "3067.HK": "iShares Hang Seng TECH ETF",
    "3110.HK": "Global X Hang Seng TECH ETF",
}

# Onshore exchange-traded funds: 15/16xxxx Shenzhen, 5xxxxx Shanghai (51/56/58/50).
_CN_ETF_PREFIXES = ("15", "16", "50", "51", "52", "56", "58")

# Book ids share a venue adapter. Keep this map here so ``markets`` does not
# import ``paper`` at module load (that cycle goes assets → paper.books →
# paper.__init__ → broker → assets).
_BOOK_VENUE = {
    "us": "us",
    "us_book": "us",
    "hk": "hk",
    "hk_theme": "hk",
    "cn": "cn",
    "cn_etf": "cn",
    "cl": "cl",
}


def _venue(market_id: str) -> str:
    raw = (market_id or "").strip()
    return _BOOK_VENUE.get(raw, raw)


def _hk_code(symbol: str) -> str:
    s = symbol.strip().upper()
    if s.endswith(".HK"):
        s = s[: -len(".HK")]
    return s.lstrip("0") or "0"


def asset_class(market_id: str, symbol: str) -> str:
    """Return equity, etf, option, or warrant."""
    venue = _venue(market_id)
    sym = symbol.strip().upper()
    if _US_OPTION.match(sym):
        return "option"
    if venue == "us":
        if sym in US_ETFS:
            return "etf"
        return "equity"
    if venue == "hk":
        padded = f"{int(_hk_code(sym)):04d}.HK" if _hk_code(sym).isdigit() else sym
        # 5-digit numeric codes are warrants / CBBCs (轮证); ETFs override by list.
        if padded in HK_ETFS or sym in HK_ETFS:
            return "etf"
        code = _hk_code(sym)
        if code.isdigit() and len(str(int(code))) >= 5:
            return "warrant"
        return "equity"
    if venue == "cn":
        code = sym.split(".")[0].zfill(6)
        if code.startswith(_CN_ETF_PREFIXES):
            return "etf"
        return "equity"
    if venue == "cl":
        return "equity"
    return "equity"


def multiplier(market_id: str, symbol: str) -> int:
    """Contract multiplier applied to cash (US listed options = 100)."""
    if asset_class(market_id, symbol) == "option":
        return 100
    return 1


def us_option_root(symbol: str) -> str | None:
    """Underlying root from an OCC option symbol, else None."""
    m = _US_OPTION.match(symbol.strip().upper())
    return m.group(1) if m else None


def is_allowed(market_id: str, symbol: str) -> bool:
    venue = _venue(market_id)
    allowed = ALLOWED_ASSET_CLASSES.get(venue, frozenset({"equity"}))
    return asset_class(venue, symbol) in allowed


def allowed_list(market_id: str) -> list[str]:
    venue = _venue(market_id)
    return sorted(ALLOWED_ASSET_CLASSES.get(venue, frozenset({"equity"})))
