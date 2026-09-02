"""Helpers to pick US listed calls and classify OCC roots."""

from __future__ import annotations

from datetime import date

import pandas as pd

from quantit.markets.assets import us_option_root


def choose_expiry(
    expiries: list[str],
    asof: date,
    min_dte: int = 21,
    max_dte: int = 90,
) -> str | None:
    """Nearest expiry with DTE in [min_dte, max_dte], else the nearest future date."""
    future: list[tuple[int, str]] = []
    for raw in expiries:
        try:
            d = date.fromisoformat(str(raw)[:10])
        except ValueError:
            continue
        dte = (d - asof).days
        if dte < 0:
            continue
        future.append((dte, d.isoformat()))
    if not future:
        return None
    in_band = [row for row in future if min_dte <= row[0] <= max_dte]
    pool = in_band or future
    pool.sort()
    return pool[0][1]


def pick_atm_call(calls: pd.DataFrame, spot: float) -> str | None:
    """Return the OCC contractSymbol whose strike is closest to ``spot``."""
    if calls is None or calls.empty or "strike" not in calls.columns:
        return None
    if "contractSymbol" not in calls.columns:
        return None
    idx = (calls["strike"].astype(float) - float(spot)).abs().idxmin()
    sym = calls.loc[idx, "contractSymbol"]
    if pd.isna(sym) or not str(sym).strip():
        return None
    occ = str(sym).strip().upper()
    if us_option_root(occ) is None:
        return None
    return occ


def yahoo_atm_call(underlying: str, spot: float, asof: date | None = None) -> str | None:
    """Best-effort Yahoo ATM call. Returns None if the chain is missing."""
    import yfinance as yf

    asof = asof or date.today()
    ticker = yf.Ticker(underlying)
    try:
        expiries = list(getattr(ticker, "options", ()) or [])
    except Exception:
        return None
    expiry = choose_expiry(expiries, asof)
    if expiry is None:
        return None
    try:
        chain = ticker.option_chain(expiry)
    except Exception:
        return None
    calls = getattr(chain, "calls", None)
    return pick_atm_call(calls, spot)
