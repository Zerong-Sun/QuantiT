"""JSONL research trace."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from closeloop.factors.spec import FactorSpec
from closeloop.validate.gates import GateReport


def default_trace_path(artifacts_dir: Path) -> Path:
    return Path(artifacts_dir) / "trace.jsonl"


def append_trace(
    artifacts_dir: Path,
    spec: FactorSpec,
    report: GateReport,
    extra: dict | None = None,
) -> Path:
    path = default_trace_path(artifacts_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "name": spec.name,
        "alpha_id": spec.padded_id(),
        "params": spec.params,
        **report.to_dict(),
    }
    if extra:
        row.update(extra)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path
