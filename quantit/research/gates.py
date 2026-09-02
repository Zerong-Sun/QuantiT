"""Gate: OOS Sharpe, drawdown, trades. Buy-and-hold Sharpe is reported, not a hard fail."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GateResult:
    passed: bool
    reasons: tuple[str, ...]


def fold_regime(buy_hold_sharpe: float) -> str:
    """Tag an OOS fold from buy-and-hold Sharpe: bull / bear / flat."""
    if buy_hold_sharpe > 0.5:
        return "bull"
    if buy_hold_sharpe < 0.0:
        return "bear"
    return "flat"


def evaluate_gates(
    oos_sharpe: float,
    oos_drawdown: float,
    oos_trades: float,
    buy_hold_sharpe: float = 0.0,
    buy_hold_drawdown: float = 0.0,
    min_sharpe: float = 0.0,
    max_drawdown: float = -0.25,
    min_trades: float = 4.0,
) -> GateResult:
    reasons: list[str] = []
    if oos_sharpe <= min_sharpe:
        reasons.append(f"OOS Sharpe {oos_sharpe:.2f} is not above {min_sharpe:.2f}")
    dd_ok = oos_drawdown >= max_drawdown or oos_drawdown >= buy_hold_drawdown
    if not dd_ok:
        reasons.append(
            f"OOS max drawdown {oos_drawdown:.2%} is worse than {max_drawdown:.2%} "
            f"and worse than buy-and-hold {buy_hold_drawdown:.2%}"
        )
    if oos_trades < min_trades:
        reasons.append(f"OOS trades {oos_trades:.0f} below minimum {min_trades:.0f}")
    return GateResult(passed=not reasons, reasons=tuple(reasons))
