"""Write promoted params for tsmom (US), hk_quality_book (HK), and cn_quality_book (CN)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quantit.research.gates import GateResult
from quantit.research.params import load_active_params, write_active_params
from quantit.research.specs import get_spec
from quantit.research.universes import universe_allows_promote


def maybe_promote(
    strategy_id: str,
    params: dict[str, Any],
    gate: GateResult,
    path: str | Path | None = None,
    *,
    symbols: list[str] | None = None,
    promote_gate: GateResult | None = None,
) -> Path | None:
    """Persist params when the spec allows promote, the universe is the paper pool, and gates pass.

    ``gate`` is the report gate. ``promote_gate`` is required and must pass.
    Nasdaq / contrast universes and an empty symbol list never write ``active_params.yaml``.
    """
    spec = get_spec(strategy_id)
    if not spec.promote or not gate.passed:
        return None
    if promote_gate is None or not promote_gate.passed:
        return None
    if not universe_allows_promote(strategy_id, symbols):
        return None
    existing = load_active_params(path)
    strategies = dict(existing.get("strategies") or {})
    strategies[strategy_id] = dict(params)
    payload = {
        **existing,
        "strategies": strategies,
        "promoted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "gate_reasons": list(promote_gate.reasons if promote_gate is not None else gate.reasons),
    }
    if strategy_id == "tsmom":
        payload["us_primary"] = "tsmom"
    elif strategy_id == "hk_quality_book":
        payload["hk_primary"] = "hk_quality_book"
    elif strategy_id == "cn_quality_book":
        payload["cn_primary"] = "cn_quality_book"
    return write_active_params(payload, path)
