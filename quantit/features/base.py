"""Base feature/factor class."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import pandas as pd


@dataclass
class Feature(ABC):
    """Base class for all factors/features."""

    name: str

    @abstractmethod
    def compute(self, df: pd.DataFrame) -> pd.Series:
        """Compute the feature from OHLCV data.

        Args:
            df: DataFrame with columns open, high, low, close, volume.

        Returns:
            Series with the computed feature values.
        """

    def compute_all(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute and return as a DataFrame column."""
        return pd.DataFrame({self.name: self.compute(df)})
