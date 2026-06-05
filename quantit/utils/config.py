"""Configuration management for QuantiT."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    """Global configuration."""

    cache_dir: Path = field(default_factory=lambda: Path.home() / ".quantit" / "cache")
    commission_rate: float = 0.001  # 0.1% per trade
    slippage_rate: float = 0.0005  # 0.05% slippage
    initial_cash: float = 100_000.0
    risk_free_rate: float = 0.04  # 4% annual
    trading_days_per_year: int = 252
    max_position_pct: float = 0.25  # max 25% per position
    max_drawdown_pct: float = 0.20  # stop trading at 20% drawdown

    def ensure_dirs(self) -> None:
        """Create required directories."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)


_default_config: Config | None = None


def get_config() -> Config:
    """Return the global config singleton."""
    global _default_config
    if _default_config is None:
        _default_config = Config()
        _default_config.ensure_dirs()
    return _default_config
