"""Market profile abstractions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MarketProfile:
    """Trading-venue defaults that should not leak into another market's config."""

    name: str
    currency: str
    trading_days_per_year: int = 252
    commission_rate: float = 0.001
    stamp_duty_rate: float = 0.0
    slippage_rate: float = 0.0005
    lot_size_note: str = ""

    @property
    def all_in_commission_rate(self) -> float:
        """One-way commission plus stamp duty (applied per fill)."""
        return self.commission_rate + self.stamp_duty_rate
