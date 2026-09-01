"""Feature registry for managing and computing factors."""

from __future__ import annotations

import pandas as pd

from quantit.features.base import Feature


class FeatureRegistry:
    """Registry of features with batch computation."""

    def __init__(self) -> None:
        self._features: dict[str, Feature] = {}

    def register(self, feature: Feature) -> None:
        self._features[feature.name] = feature

    def unregister(self, name: str) -> None:
        self._features.pop(name, None)

    def get(self, name: str) -> Feature | None:
        return self._features.get(name)

    def list(self) -> list[str]:
        return list(self._features.keys())

    def compute(self, df: pd.DataFrame, names: list[str] | None = None) -> pd.DataFrame:
        """Compute specified features (or all registered) and return combined DataFrame."""
        target = names or list(self._features.keys())
        result = df.copy()
        for name in target:
            feat = self._features.get(name)
            if feat is None:
                raise KeyError(f"Feature '{name}' not registered")
            computed = feat.compute_all(df)
            for col in computed.columns:
                result[col] = computed[col]
        return result


def default_registry() -> FeatureRegistry:
    """Create a registry pre-loaded with standard features."""
    from quantit.features.technical import (
        ATRFeature,
        BollingerBandsFeature,
        MACDFeature,
        MomentumFeature,
        RSIFeature,
        SMAFeature,
        VolatilityFeature,
        VolumeRatioFeature,
    )

    registry = FeatureRegistry()
    for period in [5, 10, 20, 50]:
        registry.register(SMAFeature(period=period))
    for period in [14]:
        registry.register(RSIFeature(period=period))
    registry.register(MACDFeature())
    registry.register(BollingerBandsFeature())
    registry.register(ATRFeature())
    registry.register(MomentumFeature())
    registry.register(VolatilityFeature())
    registry.register(VolumeRatioFeature())
    return registry
