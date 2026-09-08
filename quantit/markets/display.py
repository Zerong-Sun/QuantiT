"""Human-readable instrument labels for the paper terminal.

Hong Kong, A-shares, and futures show ``公司名字（股票代码）``. US equities
keep the ticker as the primary label.
"""

from __future__ import annotations

from quantit.markets.cn import CN_UNIVERSE, canonical_cn_symbol
from quantit.markets.hk import HK_NAMES
from quantit.markets.us import US_UNIVERSE

NAME_CODE_MARKETS = frozenset({"hk", "hk_theme", "cn", "cn_etf", "cl", "fut", "futures"})


def _canonical_hk(raw: str) -> str:
    s = raw.strip().upper()
    if s.endswith(".HK"):
        s = s[: -len(".HK")]
    digits = s.lstrip("0") or "0"
    if digits.isdigit():
        return f"{int(digits):04d}.HK"
    return f"{s}.HK"


def canonical_symbol(market_id: str, symbol: str) -> str:
    mid = (market_id or "").strip().lower()
    raw = (symbol or "").strip()
    if not raw:
        return raw
    if mid in {"hk", "hk_theme"}:
        return _canonical_hk(raw)
    if mid in {"cn", "cn_etf"}:
        return canonical_cn_symbol(raw)
    if mid == "cl":
        from quantit.markets.cl import normalize_cl_symbol

        return normalize_cl_symbol(raw)
    if mid == "us":
        return raw.upper()
    return raw.upper()


def lookup_name(market_id: str, symbol: str) -> str:
    """Company / product name from the static universe, or ``""`` if unknown."""
    mid = (market_id or "").strip().lower()
    if mid in {"hk", "hk_theme"}:
        return HK_NAMES.get(_canonical_hk(symbol), "")
    if mid in {"cn", "cn_etf"}:
        return CN_UNIVERSE.get(canonical_cn_symbol(symbol), "")
    if mid == "cl":
        from quantit.markets.cl import normalize_cl_symbol

        inst = normalize_cl_symbol(symbol)
        if inst.startswith("SH"):
            return CN_UNIVERSE.get(f"{inst[2:]}.SS", "")
        if inst.startswith("SZ"):
            return CN_UNIVERSE.get(f"{inst[2:]}.SZ", "")
        return CN_UNIVERSE.get(canonical_cn_symbol(symbol), "")
    if mid == "us":
        return US_UNIVERSE.get(symbol.strip().upper(), "")
    return ""


def display_label(market_id: str, symbol: str, name: str | None = None) -> str:
    """Label shown in the UI.

    HK / CN / futures: ``Tencent（0700.HK）``. US: ``AAPL``.
    """
    mid = (market_id or "").strip().lower()
    canon = canonical_symbol(mid, symbol)
    label = (name or lookup_name(mid, canon) or "").strip()
    if mid not in NAME_CODE_MARKETS:
        return canon or symbol
    if not label or label == canon:
        return canon or symbol
    return f"{label}（{canon}）"
