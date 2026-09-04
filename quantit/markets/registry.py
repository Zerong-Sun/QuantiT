"""In-process registry of market adapters."""

from __future__ import annotations

from quantit.markets.adapter import MarketAdapter

_default: MarketRegistry | None = None


class MarketRegistry:
    """Lookup table keyed by ``market_id`` (``us`` / ``hk`` / ``cn`` / ``cl``)."""

    def __init__(self) -> None:
        self._adapters: dict[str, MarketAdapter] = {}

    def register(self, adapter: MarketAdapter) -> None:
        self._adapters[adapter.market_id] = adapter

    def get(self, market_id: str) -> MarketAdapter:
        try:
            return self._adapters[market_id]
        except KeyError as exc:
            raise KeyError(f"Unknown market: {market_id}") from exc

    def ids(self) -> list[str]:
        return list(self._adapters)

    def all(self) -> list[MarketAdapter]:
        return list(self._adapters.values())


def default_registry() -> MarketRegistry:
    """Build a registry with US/HK/CN paper venues plus the isolated ``cl`` book."""
    from quantit.markets.cl import CLAdapter
    from quantit.markets.cn import CNAdapter
    from quantit.markets.hk import HKAdapter
    from quantit.markets.us import USAdapter

    registry = MarketRegistry()
    registry.register(USAdapter())
    registry.register(HKAdapter())
    registry.register(CNAdapter())
    registry.register(CLAdapter())
    return registry


def get_registry() -> MarketRegistry:
    """Process-wide registry, created on first use."""
    global _default
    if _default is None:
        _default = default_registry()
    return _default


def reset_registry() -> None:
    """Drop the singleton (tests)."""
    global _default
    _default = None
