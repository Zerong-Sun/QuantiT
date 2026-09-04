"""FactorSpec consumed by the loop and the RD-Agent sidecar."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FactorSpec:
    name: str
    alpha_id: str
    params: dict[str, float] = field(default_factory=dict)
    expression: str | None = None

    def padded_id(self) -> str:
        raw = str(self.alpha_id).strip()
        if raw.lower() == "custom":
            return "custom"
        return raw.zfill(3)

    def sign(self) -> float:
        value = float(self.params.get("sign", 1.0))
        return -1.0 if value < 0 else 1.0
