"""Configuration management for QuantiT."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv() -> None:
    """Load KEY=VALUE pairs from a local .env if present. Does not override existing env."""
    candidates = [
        Path.cwd() / ".env",
        Path(__file__).resolve().parents[2] / ".env",
    ]
    seen: set[Path] = set()
    for path in candidates:
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if resolved in seen or not resolved.is_file():
            continue
        seen.add(resolved)
        for raw in resolved.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("'").strip('"')
            if key:
                os.environ.setdefault(key, value)


_load_dotenv()


@dataclass
class Config:
    """Global configuration."""

    cache_dir: Path = field(default_factory=lambda: Path.home() / ".quantit" / "cache")
    commission_rate: float = 0.001  # 0.1% per trade
    slippage_rate: float = 0.0005  # 0.05% slippage
    initial_cash: float = 100_000.0
    risk_free_rate: float = 0.04  # 4% annual
    trading_days_per_year: int = 252
    max_position_pct: float = 0.25  # max 25% per position (not enforced yet)
    max_drawdown_pct: float = 0.20  # stop trading at 20% drawdown (not enforced yet)
    fill_on: str = "next_open"  # "next_open" or "same_close"
    finnhub_api_key: str = field(
        default_factory=lambda: os.environ.get("FINNHUB_API_KEY")
        or os.environ.get("QUANTIT_FINNHUB_API_KEY")
        or ""
    )

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
