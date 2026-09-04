"""Same-parameter next_open vs close+slippage comparison (synthetic, no network)."""

from __future__ import annotations

import pandas as pd

from quantit.research.fills import compare_fill_models


def _gap_bars(n: int = 80, start: str = "2020-01-02") -> pd.DataFrame:
    dates = pd.date_range(start, periods=n, freq="B")
    close = [100.0 + i * 0.4 for i in range(n)]
    # Opens gap away from the prior close so next_open fills differ from same_close.
    open_px = [c * 1.01 for c in close]
    return pd.DataFrame(
        {
            "open": open_px,
            "high": [o + 0.5 for o in open_px],
            "low": [c - 0.5 for c in close],
            "close": close,
            "volume": [1_000_000.0] * n,
        },
        index=dates,
    )


def test_compare_fill_models_reports_delta() -> None:
    data = _gap_bars()
    row = compare_fill_models(
        "tsmom",
        {"lookback": 20, "skip": 0, "target_vol": 0.15, "vol_lookback": 10},
        data,
        symbol="GAP",
        initial_cash=100_000.0,
        slippage_rate=0.0005,
    )
    assert "next_open" in row and "same_close_slip" in row
    assert "delta_sharpe" in row and "delta_dd" in row
    assert row["next_open"].get("sharpe_ratio") is not None
    assert row["same_close_slip"].get("sharpe_ratio") is not None
    assert row["fill_on_research"] == "next_open"
    assert row["fill_on_paper"] == "same_close"
    assert row["research_matches_walk_forward"] is True
