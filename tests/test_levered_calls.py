"""Levered ATM-call overlay: premiums, expiry, no 末日 contracts."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from quantit.markets.derivatives import choose_expiry
from quantit.research.levered_calls import (
    OverlayConfig,
    atm_strike,
    bs_call,
    pick_standard_expiry,
    run_levered_call_book,
    third_fridays,
)


def _ohlcv(prices: list[float], start: str = "2018-01-01") -> pd.DataFrame:
    dates = pd.date_range(start, periods=len(prices), freq="B")
    return pd.DataFrame(
        {
            "open": prices,
            "high": [p + 0.5 for p in prices],
            "low": [max(0.1, p - 0.5) for p in prices],
            "close": prices,
            "volume": [1_000_000.0] * len(prices),
        },
        index=dates,
    )


def test_bs_call_at_least_intrinsic() -> None:
    prem, delta = bs_call(100.0, 100.0, 60, 0.20)
    assert prem > 0
    assert 0 < delta < 1
    expired, _ = bs_call(110.0, 100.0, 0, 0.20)
    assert expired == pytest.approx(10.0)


def test_choose_expiry_skips_front_week() -> None:
    asof = date(2024, 6, 10)
    picked = choose_expiry(["2024-06-14", "2024-07-19", "2024-08-16"], asof, min_dte=21, max_dte=90)
    assert picked == "2024-07-19"
    dte = (date.fromisoformat(picked) - asof).days
    assert dte >= 21


def test_third_friday_and_band() -> None:
    fridays = third_fridays(date(2024, 1, 1), date(2024, 6, 30))
    assert date(2024, 1, 19) in fridays
    picked = pick_standard_expiry(date(2024, 6, 10), fridays, min_dte=21, max_dte=90)
    assert picked is not None
    assert (picked - date(2024, 6, 10)).days >= 21


def test_longest_expiry_and_itm_strike() -> None:
    fridays = third_fridays(date(2024, 1, 1), date(2024, 12, 31))
    asof = date(2024, 3, 1)
    near = pick_standard_expiry(asof, fridays, min_dte=60, max_dte=270, prefer="nearest")
    far = pick_standard_expiry(asof, fridays, min_dte=60, max_dte=270, prefer="longest")
    assert near is not None and far is not None
    assert (far - asof).days >= (near - asof).days
    assert atm_strike(100.0 * 0.85) < 100.0


def test_sticky_strikes_do_not_retarget_daily() -> None:
    n = 400
    book = {
        "AAA": _ohlcv([100.0 + i * 0.4 for i in range(n)]),
        "BBB": _ohlcv([80.0 + i * 0.35 for i in range(n)]),
    }
    cfg = OverlayConfig(
        lookback=60, skip=5, target_vol=0.15, min_dte=21, max_dte=90, sticky_strikes=True
    )
    result = run_levered_call_book(book, initial_cash=100_000, cfg=cfg)
    tags = {s for s, p in result.portfolio.positions.items() if p.quantity > 0 and s not in book}
    retarget = OverlayConfig(
        lookback=60, skip=5, target_vol=0.15, min_dte=21, max_dte=90, sticky_strikes=False
    )
    churn = run_levered_call_book(book, initial_cash=100_000, cfg=retarget)
    churn_tags = {s for s, p in churn.portfolio.positions.items() if p.quantity != 0 and s not in book}
    sticky_seen = {s for s in result.portfolio.positions if s not in book}
    churn_seen = {s for s in churn.portfolio.positions if s not in book}
    assert len(tags) <= 2
    assert len(churn_seen) > len(sticky_seen)
    assert result.metrics["final_equity"] > 100_000


def test_uptrend_call_overlay_beats_cash_and_avoids_front_month() -> None:
    n = 400
    book = {
        "AAA": _ohlcv([100.0 + i * 0.4 for i in range(n)]),
        "BBB": _ohlcv([80.0 + i * 0.35 for i in range(n)]),
    }
    cfg = OverlayConfig(lookback=60, skip=5, target_vol=0.15, min_dte=21, max_dte=90)
    result = run_levered_call_book(book, initial_cash=100_000, cfg=cfg)
    assert result.metrics["final_equity"] > 100_000
    tags = [s for s, p in result.portfolio.positions.items() if p.quantity > 0 and s not in book]
    asof = pd.Timestamp(book["AAA"].index[-1]).date()
    for tag in tags:
        # YYMMDD starts after the underlying letters; last 15 chars: yymmdd C strike
        yymmdd = tag[-15:-9]
        exp = date(2000 + int(yymmdd[:2]), int(yymmdd[2:4]), int(yymmdd[4:6]))
        assert (exp - asof).days >= 21
