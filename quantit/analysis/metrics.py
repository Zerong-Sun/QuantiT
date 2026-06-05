"""Performance metrics for backtest results."""

from __future__ import annotations

import numpy as np
import pandas as pd

from quantit.engine.backtester import BacktestResult
from quantit.utils.config import get_config


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

    win_trades = [t for t in result.trades if t.side.value == "sell"]
    total_trades = len(result.trades)

    metrics = {
        "total_return": float(total_return),
        "annual_return": float(annual_return),
        "sharpe_ratio": float(sharpe),
        "sortino_ratio": float(sortino),
        "max_drawdown": float(max_drawdown),
        "calmar_ratio": float(calmar),
        "volatility": float(returns.std() * np.sqrt(config.trading_days_per_year)),
        "total_trades": float(total_trades),
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
        f"Final Equity:    ${metrics.get('final_equity', 0):>10,.2f}",
    ]
    return "\n".join(lines)
