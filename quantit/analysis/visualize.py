"""Visualization module for backtest results."""

from __future__ import annotations

import pandas as pd

from quantit.engine.backtester import BacktestResult

try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
except ImportError:
    go = None  # type: ignore[assignment]
    make_subplots = None  # type: ignore[assignment]


def plot_equity_curve(result: BacktestResult) -> "go.Figure":
    """Plot equity curve with drawdown overlay."""
    if go is None:
        raise ImportError("plotly is required for visualization")

    equity = result.equity_curve
    cummax = equity.cummax()
    drawdown = (equity - cummax) / cummax

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        row_heights=[0.7, 0.3],
        subplot_titles=("Equity Curve", "Drawdown"),
    )

    fig.add_trace(
        go.Scatter(
            x=equity.index,
            y=equity.values,
            name="Equity",
            line=dict(color="#2196F3", width=1.5),
        ),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            x=drawdown.index,
            y=drawdown.values,
            name="Drawdown",
            fill="tozeroy",
            fillcolor="rgba(244,67,54,0.3)",
            line=dict(color="#F44336", width=1),
        ),
        row=2,
        col=1,
    )

    fig.update_layout(
        title=f"Backtest: {result.symbol} ({result.start.date()} to {result.end.date()})",
        height=600,
        template="plotly_white",
        showlegend=True,
    )
    fig.update_yaxes(title_text="Equity ($)", row=1, col=1)
    fig.update_yaxes(title_text="Drawdown %", row=2, col=1, tickformat=".1%")
    return fig


def plot_price_with_trades(result: BacktestResult, data: pd.DataFrame) -> "go.Figure":
    """Plot OHLCV with trade markers."""
    if go is None:
        raise ImportError("plotly is required for visualization")

    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=data.index,
            y=data["close"],
            name="Close",
            line=dict(color="#2196F3", width=1),
        )
    )

    buy_trades = [t for t in result.trades if t.side.value == "buy"]
    sell_trades = [t for t in result.trades if t.side.value == "sell"]

    if buy_trades:
        fig.add_trace(
            go.Scatter(
                x=[t.timestamp for t in buy_trades],
                y=[t.price for t in buy_trades],
                mode="markers",
                name="Buy",
                marker=dict(symbol="triangle-up", color="#4CAF50", size=10),
            )
        )

    if sell_trades:
        fig.add_trace(
            go.Scatter(
                x=[t.timestamp for t in sell_trades],
                y=[t.price for t in sell_trades],
                mode="markers",
                name="Sell",
                marker=dict(symbol="triangle-down", color="#F44336", size=10),
            )
        )

    fig.update_layout(
        title=f"{result.symbol} Price with Trades",
        height=400,
        template="plotly_white",
        xaxis_title="Date",
        yaxis_title="Price ($)",
    )
    return fig


def plot_indicators(data: pd.DataFrame, indicators: dict[str, pd.Series]) -> "go.Figure":
    """Plot price with overlay indicators."""
    if go is None:
        raise ImportError("plotly is required for visualization")

    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=data.index,
            y=data["close"],
            name="Close",
            line=dict(color="#2196F3", width=1),
        )
    )

    colors = ["#FF9800", "#4CAF50", "#9C27B0", "#F44336", "#00BCD4"]
    for i, (name, series) in enumerate(indicators.items()):
        fig.add_trace(
            go.Scatter(
                x=data.index,
                y=series.values,
                name=name,
                line=dict(color=colors[i % len(colors)], width=1, dash="dash"),
            )
        )

    fig.update_layout(
        title="Price with Indicators",
        height=400,
        template="plotly_white",
        xaxis_title="Date",
        yaxis_title="Price ($)",
    )
    return fig
