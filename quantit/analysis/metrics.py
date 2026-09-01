"""Performance metrics for backtest results."""

from __future__ import annotations

from collections import deque

import numpy as np

from quantit.engine.backtester import BacktestResult
from quantit.engine.broker import OrderSide, Trade
from quantit.utils.config import get_config


def _round_trip_win_rate(trades: list[Trade]) -> float:
    """FIFO-match buys with sells; a closed lot wins if sell price > buy price."""
    lots: deque[list[float]] = deque()
    wins = 0
    closed = 0
    for trade in trades:
        if trade.side == OrderSide.BUY:
            lots.append([float(trade.quantity), float(trade.price)])
            continue
        remaining = float(trade.quantity)
        while remaining > 0 and lots:
            lot_qty, lot_price = lots[0]
            matched = min(remaining, lot_qty)
            closed += 1
            if trade.price > lot_price:
                wins += 1
            lot_qty -= matched
            remaining -= matched
            if lot_qty <= 0:
                lots.popleft()
            else:
                lots[0][0] = lot_qty
    if closed == 0:
        return 0.0
    return wins / closed


def compute_metrics(result: BacktestResult) -> dict[str, float]:
    """Compute standard performance metrics from a backtest result."""
    config = get_config()
    equity = result.equity_curve
    if equity.empty or len(equity) < 2:
        return {}

    returns = equity.pct_change().dropna()
    total_return = (equity.iloc[-1] / equity.iloc[0]) - 1

    days = (equity.index[-1] - equity.index[0]).days
    years = max(days / 365.25, 1 / 365.25)
    annual_return = (1 + total_return) ** (1 / years) - 1

    rf_daily = config.risk_free_rate / config.trading_days_per_year
    excess = returns - rf_daily
    sharpe = (
        np.sqrt(config.trading_days_per_year) * excess.mean() / excess.std()
        if excess.std() > 0
        else 0.0
    )

    downside = returns[returns < 0]
    sortino = (
        np.sqrt(config.trading_days_per_year) * excess.mean() / downside.std()
        if len(downside) > 0 and downside.std() > 0
        else 0.0
    )

    cummax = equity.cummax()
    drawdown = (equity - cummax) / cummax
    max_drawdown = drawdown.min()

    calmar = annual_return / abs(max_drawdown) if max_drawdown != 0 else 0.0

    total_trades = len(result.trades)
    win_rate = _round_trip_win_rate(result.trades)

    metrics = {
        "total_return": float(total_return),
        "annual_return": float(annual_return),
        "sharpe_ratio": float(sharpe),
        "sortino_ratio": float(sortino),
        "max_drawdown": float(max_drawdown),
        "calmar_ratio": float(calmar),
        "volatility": float(returns.std() * np.sqrt(config.trading_days_per_year)),
        "total_trades": float(total_trades),
        "win_rate": float(win_rate),
        "final_equity": float(equity.iloc[-1]),
        "initial_equity": float(equity.iloc[0]),
    }

    result.metrics = metrics
    return metrics


def format_metrics(metrics: dict[str, float]) -> str:
    """Format metrics as a readable string."""
    if not metrics:
        return "No metrics available."

    lines = [
        f"Total Return:    {metrics.get('total_return', 0):>10.2%}",
        f"Annual Return:   {metrics.get('annual_return', 0):>10.2%}",
        f"Sharpe Ratio:    {metrics.get('sharpe_ratio', 0):>10.2f}",
        f"Sortino Ratio:   {metrics.get('sortino_ratio', 0):>10.2f}",
        f"Max Drawdown:    {metrics.get('max_drawdown', 0):>10.2%}",
        f"Calmar Ratio:    {metrics.get('calmar_ratio', 0):>10.2f}",
        f"Volatility:      {metrics.get('volatility', 0):>10.2%}",
        f"Total Trades:    {metrics.get('total_trades', 0):>10.0f}",
        f"Win Rate:        {metrics.get('win_rate', 0):>10.2%}",
        f"Final Equity:    ${metrics.get('final_equity', 0):>10,.2f}",
    ]
    return "\n".join(lines)
