"""Paper vs research fill models. Not a parameter-search path."""

from __future__ import annotations

from typing import Any

import pandas as pd

from quantit.research.search import run_backtest


def compare_fill_models(
    strategy_id: str,
    params: dict[str, Any],
    data: pd.DataFrame | dict[str, pd.DataFrame],
    symbol: str,
    initial_cash: float = 100_000.0,
    extra: dict[str, Any] | None = None,
    slippage_rate: float = 0.0005,
    commission_rate: float | None = None,
) -> dict[str, Any]:
    """Run the same params on next_open (walk-forward defaults) vs same_close+slip (paper).

    The research arm leaves commission/slippage at config defaults, matching
    ``walk_forward`` / ``run_backtest(initial_cash=...)``. The paper arm only
    changes fill timing and venue slippage.
    """
    research = run_backtest(
        strategy_id,
        params,
        data,
        symbol,
        initial_cash,
        extra,
        fill_on="next_open",
    )
    paper = run_backtest(
        strategy_id,
        params,
        data,
        symbol,
        initial_cash,
        extra,
        fill_on="same_close",
        slippage_rate=slippage_rate,
        commission_rate=commission_rate,
    )
    m0 = research["metrics"]
    m1 = paper["metrics"]
    return {
        "next_open": m0,
        "same_close_slip": m1,
        "delta_sharpe": float(m1.get("sharpe_ratio") or 0.0) - float(m0.get("sharpe_ratio") or 0.0),
        "delta_dd": float(m1.get("max_drawdown") or 0.0) - float(m0.get("max_drawdown") or 0.0),
        "fill_on_research": "next_open",
        "fill_on_paper": "same_close",
        "slippage_rate": slippage_rate,
        "research_matches_walk_forward": True,
    }
