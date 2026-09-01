"""Fundamental features (placeholder for earnings/financial data)."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from quantit.features.base import Feature


@dataclass
class PriceToEarningsFeature(Feature):
    """P/E ratio — requires earnings data in the DataFrame."""

    name: str = "pe_ratio"

    def compute(self, df: pd.DataFrame) -> pd.Series:
        if "eps" not in df.columns:
            raise ValueError("DataFrame must contain 'eps' column for P/E calculation")
        return df["close"] / df["eps"].replace(0, float("nan"))


@dataclass
class PriceToBookFeature(Feature):
    """P/B ratio — requires book value data in the DataFrame."""

    name: str = "pb_ratio"

    def compute(self, df: pd.DataFrame) -> pd.Series:
        if "book_value" not in df.columns:
            raise ValueError("DataFrame must contain 'book_value' column for P/B calculation")
        return df["close"] / df["book_value"].replace(0, float("nan"))


@dataclass
class EarningsYieldFeature(Feature):
    """Earnings yield (inverse P/E)."""

    name: str = "earnings_yield"

    def compute(self, df: pd.DataFrame) -> pd.Series:
        if "eps" not in df.columns:
            raise ValueError("DataFrame must contain 'eps' column")
        return df["eps"] / df["close"].replace(0, float("nan"))
