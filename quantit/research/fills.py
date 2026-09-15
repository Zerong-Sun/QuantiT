"""Paper vs research fill models. Not a parameter-search path.

F2 fill-timing contract — **intentional difference**, not a bug:

* Research / walk-forward uses ``next_open``: a signal on bar t fills at
  bar t+1 **open** ± slippage (``Config.fill_on``). Unfilled last-bar
  orders are cancelled.
* Paper (US/HK/CN books and ``cl`` via ``PaperBroker``) fills immediately
  at the delayed last print: ``MarketAdapter.fetch_quote().last`` is the
  last daily **close** with ``delayed=True``. There is no next-open queue.
* The closest backtest analog of paper is ``same_close``. Do not "align"
  walk-forward onto same-close or paper onto next-open without an explicit
  product change; ``tests/test_fills.py`` locks this split.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from quantit.research.search import run_backtest
from quantit.utils.config import get_config

RESEARCH_FILL_ON = "next_open"
PAPER_FILL_ANALOG = "same_close"


def apply_slippage(price: float, *, side: str, slippage_rate: float) -> float:
    """Match engine ``Broker`` and ``PaperBroker``: buy pays up, sell receives down."""
    slip = float(price) * float(slippage_rate)
    side_l = side.lower()
    if side_l == "buy":
        return float(price) + slip
    if side_l == "sell":
        return float(price) - slip
    raise ValueError(f"unsupported side: {side}")


def research_fill_price(
    next_open: float,
    *,
    side: str = "buy",
    slippage_rate: float = 0.0,
) -> float:
    """Fill price for research / walk-forward (next bar's open)."""
    return apply_slippage(next_open, side=side, slippage_rate=slippage_rate)


def paper_fill_price(
    delayed_last_close: float,
    *,
    side: str = "buy",
    slippage_rate: float = 0.0,
) -> float:
    """Fill price for paper (delayed last print = last daily close)."""
    return apply_slippage(delayed_last_close, side=side, slippage_rate=slippage_rate)


def research_uses_walk_forward_fill() -> bool:
    """True when config still matches walk-forward (``next_open``)."""
    return get_config().fill_on == RESEARCH_FILL_ON


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

    The research arm uses the same costs as ``walk_forward`` / ``run_backtest``
    (config defaults, or CN_PROFILE buy/sell+stamp for CN studies). The paper
    arm only changes fill timing and venue slippage.
    """
    research = run_backtest(
        strategy_id,
        params,
        data,
        symbol,
        initial_cash,
        extra,
        fill_on=RESEARCH_FILL_ON,
    )
    paper = run_backtest(
        strategy_id,
        params,
        data,
        symbol,
        initial_cash,
        extra,
        fill_on=PAPER_FILL_ANALOG,
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
        "fill_on_research": RESEARCH_FILL_ON,
        "fill_on_paper": PAPER_FILL_ANALOG,
        "slippage_rate": slippage_rate,
        "research_matches_walk_forward": research_uses_walk_forward_fill(),
    }
