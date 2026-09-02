"""Classify paper-tradable symbols (equity / ETF / option / warrant)."""

from __future__ import annotations

import re

# What the paper book is allowed to trade, including auto overlay for
# US listed calls and HK 5-digit warrants / CBBCs.
ALLOWED_ASSET_CLASSES: dict[str, frozenset[str]] = {
    "us": frozenset({"equity", "etf", "option"}),
    "hk": frozenset({"equity", "etf", "warrant"}),
    "cn": frozenset({"equity", "etf"}),
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


def _hk_code(symbol: str) -> str:
    s = symbol.strip().upper()
    if s.endswith(".HK"):
        s = s[: -len(".HK")]
    return s.lstrip("0") or "0"


def asset_class(market_id: str, symbol: str) -> str:
    """Return equity, etf, option, or warrant."""
    sym = symbol.strip().upper()
    if _US_OPTION.match(sym):
        return "option"
    if market_id == "us":
        if sym in US_ETFS:
            return "etf"
        return "equity"
    if market_id == "hk":
        padded = f"{int(_hk_code(sym)):04d}.HK" if _hk_code(sym).isdigit() else sym
        # 5-digit numeric codes are warrants / CBBCs (轮证); ETFs override by list.
        if padded in HK_ETFS or sym in HK_ETFS:
            return "etf"
        code = _hk_code(sym)
        if code.isdigit() and len(str(int(code))) >= 5:
            return "warrant"
        return "equity"
    if market_id == "cn":
        code = sym.split(".")[0].zfill(6)
        if code.startswith(_CN_ETF_PREFIXES):
            return "etf"
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
    allowed = ALLOWED_ASSET_CLASSES.get(market_id, frozenset({"equity"}))
    return asset_class(market_id, symbol) in allowed


def allowed_list(market_id: str) -> list[str]:
    return sorted(ALLOWED_ASSET_CLASSES.get(market_id, frozenset({"equity"})))
