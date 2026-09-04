"""Report gates vs promote gates.

Report: OOS Sharpe > 0, drawdown, trades. Buy-and-hold Sharpe is shown, not a hard fail.
Promote: report plus OOS Sharpe ≥ BH or Calmar-like advantage, and two bear folds that hold.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable


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


def calmar_like(sharpe: float, drawdown: float) -> float:
    """Study-level Calmar proxy: Sharpe / |max DD|."""
    if not math.isfinite(float(sharpe)):
        return 0.0
    dd = float(drawdown)
    if dd >= 0.0 or abs(dd) < 1e-12:
        return math.inf if sharpe > 0.0 else 0.0
    return float(sharpe) / abs(dd)


def _calmar_advantage(oos_c: float, bh_c: float) -> bool:
    """True when OOS Calmar-like is a real improvement, not inf/inf noise."""
    if math.isinf(oos_c) and math.isinf(bh_c):
        return False
    if math.isinf(oos_c) and oos_c > 0:
        return True
    if math.isinf(bh_c) and bh_c > 0:
        return False
    return oos_c >= bh_c


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
    if not math.isfinite(float(oos_sharpe)) or oos_sharpe <= min_sharpe:
        reasons.append(f"OOS Sharpe {oos_sharpe:.2f} is not above {min_sharpe:.2f}")
    dd_ok = oos_drawdown >= max_drawdown or oos_drawdown >= buy_hold_drawdown
    if not math.isfinite(float(oos_drawdown)) or not dd_ok:
        reasons.append(
            f"OOS max drawdown {oos_drawdown:.2%} is worse than {max_drawdown:.2%} "
            f"and worse than buy-and-hold {buy_hold_drawdown:.2%}"
        )
    if not math.isfinite(float(oos_trades)) or oos_trades < min_trades:
        reasons.append(f"OOS trades {oos_trades:.0f} below minimum {min_trades:.0f}")
    return GateResult(passed=not reasons, reasons=tuple(reasons))


def evaluate_promote_gates(
    oos_sharpe: float,
    oos_drawdown: float,
    oos_trades: float,
    buy_hold_sharpe: float = 0.0,
    buy_hold_drawdown: float = 0.0,
    folds: Iterable[Any] | None = None,
    min_sharpe: float = 0.0,
    max_drawdown: float = -0.25,
    min_trades: float = 4.0,
    min_bear_ok: int = 2,
) -> GateResult:
    """Stricter gate used before writing active_params.yaml."""
    report = evaluate_gates(
        oos_sharpe=oos_sharpe,
        oos_drawdown=oos_drawdown,
        oos_trades=oos_trades,
        buy_hold_sharpe=buy_hold_sharpe,
        buy_hold_drawdown=buy_hold_drawdown,
        min_sharpe=min_sharpe,
        max_drawdown=max_drawdown,
        min_trades=min_trades,
    )
    reasons = list(report.reasons)
    oos_c = calmar_like(oos_sharpe, oos_drawdown)
    bh_c = calmar_like(buy_hold_sharpe, buy_hold_drawdown)
    if oos_sharpe < buy_hold_sharpe and not _calmar_advantage(oos_c, bh_c):
        reasons.append(
            f"OOS Sharpe {oos_sharpe:.2f} and Calmar-like {oos_c:.2f} lag "
            f"buy-and-hold Sharpe {buy_hold_sharpe:.2f} / {bh_c:.2f}"
        )
    bear_ok = 0
    bear_n = 0
    if folds is not None:
        for fold in folds:
            if getattr(fold, "regime", "") != "bear":
                continue
            bear_n += 1
            oos = getattr(fold, "oos_metrics", None) or {}
            bh = getattr(fold, "bh_metrics", None) or {}
            dd = float(oos.get("max_drawdown") or 0.0)
            bh_dd = float(bh.get("max_drawdown") or 0.0)
            if dd >= max_drawdown or dd >= bh_dd:
                bear_ok += 1
    if bear_ok < min_bear_ok:
        reasons.append(
            f"bear folds within drawdown {bear_ok} < {min_bear_ok} (n={bear_n})"
        )
    return GateResult(passed=not reasons, reasons=tuple(reasons))
