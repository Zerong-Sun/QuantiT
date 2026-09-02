"""Gate: OOS Sharpe, drawdown, trades, vs buy-and-hold."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GateResult:
    passed: bool
    reasons: tuple[str, ...]


def evaluate_gates(
    oos_sharpe: float,
    oos_drawdown: float,
    oos_trades: float,
    buy_hold_sharpe: float,
    min_sharpe: float = 0.0,
    max_drawdown: float = -0.25,
    min_trades: float = 4.0,
) -> GateResult:
    reasons: list[str] = []
    if oos_sharpe <= min_sharpe:
        reasons.append(f"OOS Sharpe {oos_sharpe:.2f} is not above {min_sharpe:.2f}")
    if oos_drawdown < max_drawdown:
        reasons.append(f"OOS max drawdown {oos_drawdown:.2%} is worse than {max_drawdown:.2%}")
    if oos_trades < min_trades:
        reasons.append(f"OOS trades {oos_trades:.0f} below minimum {min_trades:.0f}")
    if oos_sharpe < buy_hold_sharpe:
        reasons.append(
            f"OOS Sharpe {oos_sharpe:.2f} is below buy-and-hold {buy_hold_sharpe:.2f}"
        )
    return GateResult(passed=not reasons, reasons=tuple(reasons))
