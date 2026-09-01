"""HTML report generation for backtest results."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from quantit.analysis.metrics import compute_metrics
from quantit.engine.backtester import BacktestResult


def generate_report(result: BacktestResult, output_path: str | Path | None = None) -> str:
    """Generate an HTML report for a backtest result."""
    metrics = result.metrics or compute_metrics(result)
    equity = result.equity_curve
    returns = equity.pct_change().dropna()
    cummax = equity.cummax()
    drawdown = (equity - cummax) / cummax

    trade_rows = ""
    for t in result.trades[:200]:
        trade_rows += f"""
        <tr>
            <td>{t.timestamp.strftime('%Y-%m-%d')}</td>
            <td>{t.symbol}</td>
            <td style="color:{'#4CAF50' if t.side.value=='buy' else '#F44336'}">{t.side.value.upper()}</td>
            <td>{t.quantity}</td>
            <td>${t.price:.2f}</td>
            <td>${t.commission:.2f}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>QuantiT Backtest Report — {result.symbol}</title>
<style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 40px; background: #fafafa; color: #333; }}
    .header {{ text-align: center; margin-bottom: 30px; }}
    .header h1 {{ margin: 0; color: #1a73e8; }}
    .header p {{ color: #666; margin-top: 5px; }}
    .metrics {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 30px; }}
    .metric-card {{ background: white; border-radius: 8px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); text-align: center; }}
    .metric-card .label {{ font-size: 12px; color: #888; text-transform: uppercase; letter-spacing: 1px; }}
    .metric-card .value {{ font-size: 24px; font-weight: bold; margin-top: 8px; }}
    .positive {{ color: #4CAF50; }}
    .negative {{ color: #F44336; }}
    table {{ width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
    th, td {{ padding: 10px 14px; text-align: left; border-bottom: 1px solid #eee; }}
    th {{ background: #f5f5f5; font-weight: 600; font-size: 13px; color: #555; }}
    .section {{ margin: 30px 0; }}
    .section h2 {{ color: #333; border-bottom: 2px solid #1a73e8; padding-bottom: 8px; display: inline-block; }}
</style>
</head>
<body>
<div class="header">
    <h1>QuantiT Backtest Report</h1>
    <p>{result.symbol} | {result.start.strftime('%Y-%m-%d')} to {result.end.strftime('%Y-%m-%d')} | Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
</div>

<div class="metrics">
    <div class="metric-card">
        <div class="label">Total Return</div>
        <div class="value {'positive' if metrics.get('total_return',0)>=0 else 'negative'}">{metrics.get('total_return',0):.2%}</div>
    </div>
    <div class="metric-card">
        <div class="label">Annual Return</div>
        <div class="value {'positive' if metrics.get('annual_return',0)>=0 else 'negative'}">{metrics.get('annual_return',0):.2%}</div>
    </div>
    <div class="metric-card">
        <div class="label">Sharpe Ratio</div>
        <div class="value">{metrics.get('sharpe_ratio',0):.2f}</div>
    </div>
    <div class="metric-card">
        <div class="label">Sortino Ratio</div>
        <div class="value">{metrics.get('sortino_ratio',0):.2f}</div>
    </div>
    <div class="metric-card">
        <div class="label">Max Drawdown</div>
        <div class="value negative">{metrics.get('max_drawdown',0):.2%}</div>
    </div>
    <div class="metric-card">
        <div class="label">Volatility</div>
        <div class="value">{metrics.get('volatility',0):.2%}</div>
    </div>
    <div class="metric-card">
        <div class="label">Calmar Ratio</div>
        <div class="value">{metrics.get('calmar_ratio',0):.2f}</div>
    </div>
    <div class="metric-card">
        <div class="label">Total Trades</div>
        <div class="value">{int(metrics.get('total_trades',0))}</div>
    </div>
    <div class="metric-card">
        <div class="label">Final Equity</div>
        <div class="value">${metrics.get('final_equity',0):,.2f}</div>
    </div>
</div>

<div class="section">
    <h2>Trade Log (first 200)</h2>
    <table>
        <thead><tr><th>Date</th><th>Symbol</th><th>Side</th><th>Qty</th><th>Price</th><th>Commission</th></tr></thead>
        <tbody>{trade_rows}</tbody>
    </table>
</div>

</body>
</html>"""

    if output_path is not None:
        Path(output_path).write_text(html, encoding="utf-8")

    return html
