"""Persist evaluated Alpha101 records under artifacts/library/."""

from __future__ import annotations

import json
from pathlib import Path

from closeloop.factors.spec import FactorSpec
from closeloop.validate.gates import GateReport


def library_dir(artifacts: Path) -> Path:
    return Path(artifacts) / "library"


def upsert_record(
    artifacts: Path,
    spec: FactorSpec,
    report: GateReport,
    *,
    start: str,
    end: str,
    universe: str = "csi300",
) -> Path:
    folder = library_dir(artifacts)
    folder.mkdir(parents=True, exist_ok=True)
    payload = {
        "name": spec.name,
        "alpha_id": spec.padded_id(),
        "params": spec.params,
        "start": start,
        "end": end,
        "universe": universe,
        **report.to_dict(),
    }
    path = folder / f"{spec.padded_id()}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def load_library(artifacts: Path) -> list[dict]:
    folder = library_dir(artifacts)
    if not folder.exists():
        return []
    rows = []
    for path in sorted(folder.glob("*.json")):
        rows.append(json.loads(path.read_text(encoding="utf-8")))
    rows.sort(key=lambda r: abs(float(r.get("ic_mean") or 0.0)), reverse=True)
    return rows


def render_report(rows: list[dict]) -> str:
    lines = [
        "# Closeloop factor library",
        "",
        "| alpha_id | passed | ic_mean | ic_ir | quantile_spread | turnover | universe |",
        "|----------|--------|---------|-------|-----------------|----------|----------|",
    ]
    for row in rows:
        lines.append(
            "| {alpha_id} | {passed} | {ic_mean:.4f} | {ic_ir:.4f} | {quantile_spread:.4f} | {turnover:.4f} | {universe} |".format(
                alpha_id=row.get("alpha_id", ""),
                passed=row.get("passed"),
                ic_mean=float(row.get("ic_mean") or float("nan")),
                ic_ir=float(row.get("ic_ir") or float("nan")),
                quantile_spread=float(row.get("quantile_spread") or float("nan")),
                turnover=float(row.get("turnover") or float("nan")),
                universe=row.get("universe", ""),
            )
        )
    if not rows:
        lines.append("| _(empty)_ | | | | | | |")
    lines.append("")
    return "\n".join(lines)


def write_report_md(artifacts: Path) -> Path:
    rows = load_library(artifacts)
    path = library_dir(artifacts) / "REPORT.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_report(rows), encoding="utf-8")
    return path
