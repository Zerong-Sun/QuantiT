"""HTML study report: IS/OOS folds vs buy-and-hold."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from quantit.research.walk_forward import StudyResult


def _pct(value: float) -> str:
    return f"{value:.2%}"


def _num(value: float) -> str:
    return f"{value:.2f}"


def render_study(study: StudyResult, output_path: str | Path | None = None) -> str:
    gate = study.gate
    status = "PASS" if study.passed else "FAIL"
    reasons = ""
    if gate and gate.reasons:
        reasons = "<ul>" + "".join(f"<li>{r}</li>" for r in gate.reasons) + "</ul>"
    rows = ""
    show_ub = study.strategy_id == "tsmom" or any(f.us_book_metrics for f in study.folds)
    for i, fold in enumerate(study.folds, start=1):
        ub_cell = ""
        if show_ub:
            ub_cell = f"<td>{_num(float(fold.us_book_metrics.get('sharpe_ratio') or 0))}</td>"
        rows += f"""
        <tr>
            <td>{i}</td>
            <td>{fold.params}</td>
            <td>{_num(float(fold.is_metrics.get('sharpe_ratio') or 0))}</td>
            <td>{_num(float(fold.oos_metrics.get('sharpe_ratio') or 0))}</td>
            <td>{_pct(float(fold.oos_metrics.get('max_drawdown') or 0))}</td>
            <td>{int(fold.oos_metrics.get('total_trades') or 0)}</td>
            <td>{_num(float(fold.bh_metrics.get('sharpe_ratio') or 0))}</td>
            {ub_cell}
        </tr>"""
    ub_header = "<th>US book Sharpe</th>" if show_ub else ""
    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>QuantiT research — {study.strategy_id}</title>
<style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 40px; background: #fafafa; color: #333; }}
    table {{ width: 100%; border-collapse: collapse; background: white; }}
    th, td {{ padding: 8px 12px; border-bottom: 1px solid #eee; text-align: left; font-size: 13px; }}
    .fail {{ color: #c62828; }}
    .pass {{ color: #2e7d32; }}
</style>
</head>
<body>
<h1>QuantiT research study</h1>
<p>{study.strategy_id} / {study.symbol} / {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
<p class="{'pass' if study.passed else 'fail'}">Gate: {status}</p>
{reasons}
<p>OOS Sharpe {_num(study.oos_sharpe)} | OOS max DD {_pct(study.oos_drawdown)} |
OOS trades {study.oos_trades:.0f} | Buy-and-hold Sharpe {_num(study.bh_sharpe)}</p>
<p>Last-fold params: {study.best_params}</p>
<p>KPI is OOS Sharpe vs buy-and-hold, not win rate.</p>
<table>
<thead><tr><th>Fold</th><th>IS params</th><th>IS Sharpe</th><th>OOS Sharpe</th><th>OOS DD</th><th>OOS trades</th><th>BH Sharpe</th>{ub_header}</tr></thead>
<tbody>{rows}</tbody>
</table>
</body>
</html>
"""
    if output_path is not None:
        Path(output_path).write_text(html, encoding="utf-8")
    return html
