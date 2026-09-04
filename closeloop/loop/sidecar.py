"""RD-Agent sidecar: inbox YAML FactorSpec → outbox JSON GateReport.

Official microsoft/RD-Agent stays in another process. This only reads/writes files.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from closeloop.factors.spec import FactorSpec
from closeloop.validate.gates import GateReport


def default_artifacts_dir() -> Path:
    import os

    override = os.environ.get("CLOSELOOP_ARTIFACTS")
    if override:
        return Path(override).expanduser()
    return Path(__file__).resolve().parents[1] / "artifacts"


def inbox_dir(artifacts: Path) -> Path:
    return Path(artifacts) / "inbox"


def outbox_dir(artifacts: Path) -> Path:
    return Path(artifacts) / "outbox"


def read_spec(path: Path) -> FactorSpec:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"{path} is not a mapping")
    alpha_id = str(raw.get("alpha_id") or raw.get("id") or "")
    name = str(raw.get("name") or f"alpha{alpha_id}")
    params = raw.get("params") or {}
    if not isinstance(params, dict):
        params = {}
    expression = raw.get("expression")
    return FactorSpec(
        name=name,
        alpha_id=str(alpha_id),
        params={str(k): float(v) for k, v in params.items()},
        expression=str(expression) if expression else None,
    )


def write_report(path: Path, spec: FactorSpec, report: GateReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "name": spec.name,
        "alpha_id": spec.padded_id(),
        "params": spec.params,
        **report.to_dict(),
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def list_inbox(artifacts: Path) -> list[Path]:
    folder = inbox_dir(artifacts)
    if not folder.exists():
        return []
    return sorted(folder.glob("*.yaml"))
