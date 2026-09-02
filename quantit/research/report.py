"""HTML and CSV study reports: IS/OOS folds vs buy-and-hold."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from quantit.research.walk_forward import StudyResult


def _pct(value: float) -> str:
    return f"{value:.2%}"


def _num(value: float) -> str:
    return f"{value:.2f}"


def _calmar(metrics: dict) -> float:
    return float(metrics.get("calmar_ratio") or 0.0)


def write_folds_csv(study: StudyResult, output_path: str | Path) -> Path:
    dest = Path(output_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "fold",
        "test_start",
        "test_end",
        "regime",
        "params",
        "is_sharpe",
        "oos_sharpe",
        "oos_dd",
        "oos_calmar",
        "oos_trades",
        "bh_sharpe",
        "bh_dd",
        "bh_calmar",
        "us_book_sharpe",
    ]
    with dest.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for i, fold in enumerate(study.folds, start=1):
            writer.writerow(
                {
                    "fold": i,
                    "test_start": fold.test_start,
                    "test_end": fold.test_end,
                    "regime": fold.regime,
                    "params": fold.params,
                    "is_sharpe": fold.is_metrics.get("sharpe_ratio") or 0,
                    "oos_sharpe": fold.oos_metrics.get("sharpe_ratio") or 0,
                    "oos_dd": fold.oos_metrics.get("max_drawdown") or 0,
                    "oos_calmar": _calmar(fold.oos_metrics),
                    "oos_trades": fold.oos_metrics.get("total_trades") or 0,
                    "bh_sharpe": fold.bh_metrics.get("sharpe_ratio") or 0,
                    "bh_dd": fold.bh_metrics.get("max_drawdown") or 0,
                    "bh_calmar": _calmar(fold.bh_metrics),
                    "us_book_sharpe": (fold.us_book_metrics or {}).get("sharpe_ratio") or 0,
                }
            )
    return dest


def regime_summary(study: StudyResult) -> dict[str, float]:
    """Mean OOS Sharpe by bull/bear/flat fold tags."""
    buckets: dict[str, list[float]] = {"bull": [], "bear": [], "flat": []}
    for fold in study.folds:
        tag = fold.regime if fold.regime in buckets else "flat"
        buckets[tag].append(float(fold.oos_metrics.get("sharpe_ratio") or 0.0))
    out: dict[str, float] = {}
    for tag, values in buckets.items():
        out[tag] = float(sum(values) / len(values)) if values else 0.0
        out[f"{tag}_n"] = float(len(values))
    return out


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
        oos_dd = float(fold.oos_metrics.get("max_drawdown") or 0)
        bh_dd = float(fold.bh_metrics.get("max_drawdown") or 0)
        rows += f"""
        <tr>
            <td>{i}</td>
            <td>{fold.test_start} → {fold.test_end}</td>
            <td>{fold.regime}</td>
            <td>{fold.params}</td>
            <td>{_num(float(fold.is_metrics.get('sharpe_ratio') or 0))}</td>
            <td>{_num(float(fold.oos_metrics.get('sharpe_ratio') or 0))}</td>
            <td>{_pct(oos_dd)}</td>
            <td>{_num(_calmar(fold.oos_metrics))}</td>
            <td>{int(fold.oos_metrics.get('total_trades') or 0)}</td>
            <td>{_num(float(fold.bh_metrics.get('sharpe_ratio') or 0))}</td>
            <td>{_pct(bh_dd)}</td>
            <td>{_num(_calmar(fold.bh_metrics))}</td>
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
OOS trades {study.oos_trades:.0f} | Buy-and-hold Sharpe {_num(study.bh_sharpe)} |
BH max DD {_pct(study.bh_drawdown)}</p>
<p>Last-fold params: {study.best_params}</p>
<p>KPI is OOS Sharpe and drawdown vs buy-and-hold (Sharpe need not beat BH). Not win rate.</p>
<table>
<thead><tr><th>Fold</th><th>OOS window</th><th>Regime</th><th>IS params</th><th>IS Sharpe</th><th>OOS Sharpe</th><th>OOS DD</th><th>OOS Calmar</th><th>OOS trades</th><th>BH Sharpe</th><th>BH DD</th><th>BH Calmar</th>{ub_header}</tr></thead>
<tbody>{rows}</tbody>
</table>
</body>
</html>
"""
    if output_path is not None:
        Path(output_path).write_text(html, encoding="utf-8")
    return html
