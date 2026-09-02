"""Write promoted params; tsmom only by default."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quantit.research.gates import GateResult
from quantit.research.params import load_active_params, write_active_params
from quantit.research.specs import get_spec


def maybe_promote(
    strategy_id: str,
    params: dict[str, Any],
    gate: GateResult,
    path: str | Path | None = None,
) -> Path | None:
    """Persist params when the gate passed and the spec allows promote."""
    spec = get_spec(strategy_id)
    if not spec.promote or not gate.passed:
        return None
    existing = load_active_params(path)
    strategies = dict(existing.get("strategies") or {})
    strategies[strategy_id] = dict(params)
    payload = {
        **existing,
        "us_primary": strategy_id if strategy_id == "tsmom" else existing.get("us_primary", "us_book"),
        "strategies": strategies,
        "promoted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "gate_reasons": list(gate.reasons),
    }
    if strategy_id == "tsmom":
        payload["us_primary"] = "tsmom"
    return write_active_params(payload, path)
