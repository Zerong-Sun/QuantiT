"""Technical indicator features."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from quantit.features.base import Feature


@dataclass
class SMAFeature(Feature):
    """Simple Moving Average."""

    period: int = 20
    column: str = "close"
    name: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            self.name = f"sma_{self.period}"

    def compute(self, df: pd.DataFrame) -> pd.Series:
        return df[self.column].rolling(self.period).mean()


@dataclass
class EMAFeature(Feature):
    """Exponential Moving Average."""

    period: int = 20
    column: str = "close"
    name: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            self.name = f"ema_{self.period}"

    def compute(self, df: pd.DataFrame) -> pd.Series:
        return df[self.column].ewm(span=self.period, adjust=False).mean()


@dataclass
class RSIFeature(Feature):
    """Relative Strength Index."""

    period: int = 14
    column: str = "close"
    name: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            self.name = f"rsi_{self.period}"

    def compute(self, df: pd.DataFrame) -> pd.Series:
        delta = df[self.column].diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        avg_gain = gain.ewm(span=self.period, adjust=False).mean()
        avg_loss = loss.ewm(span=self.period, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        # Strict up-days: no losses → RS is infinite → RSI 100 (not NaN).
        return rsi.mask((avg_loss == 0) & (avg_gain > 0), 100.0)


@dataclass
class MACDFeature(Feature):
    """MACD (Moving Average Convergence Divergence)."""

    fast_period: int = 12
    slow_period: int = 26
    signal_period: int = 9
    name: str = "macd"

    def compute(self, df: pd.DataFrame) -> pd.Series:
        fast = df["close"].ewm(span=self.fast_period, adjust=False).mean()
        slow = df["close"].ewm(span=self.slow_period, adjust=False).mean()
        return fast - slow

    def compute_all(self, df: pd.DataFrame) -> pd.DataFrame:
        macd = self.compute(df)
        signal = macd.ewm(span=self.signal_period, adjust=False).mean()
        histogram = macd - signal
        return pd.DataFrame(
            {
                "macd": macd,
                "macd_signal": signal,
                "macd_hist": histogram,
            }
        )


@dataclass
class BollingerBandsFeature(Feature):
    """Bollinger Bands."""

    period: int = 20
    num_std: float = 2.0
    name: str = "bb"

    def compute(self, df: pd.DataFrame) -> pd.Series:
        sma = df["close"].rolling(self.period).mean()
        std = df["close"].rolling(self.period).std()
        return (df["close"] - sma) / (std * self.num_std)

    def compute_all(self, df: pd.DataFrame) -> pd.DataFrame:
        sma = df["close"].rolling(self.period).mean()
        std = df["close"].rolling(self.period).std()
        return pd.DataFrame(
            {
                "bb_mid": sma,
                "bb_upper": sma + std * self.num_std,
                "bb_lower": sma - std * self.num_std,
                "bb_pct": (df["close"] - sma) / (std * self.num_std),
            }
        )


@dataclass
class ATRFeature(Feature):
    """Average True Range."""

    period: int = 14
    name: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            self.name = f"atr_{self.period}"

    def compute(self, df: pd.DataFrame) -> pd.Series:
        high = df["high"]
        low = df["low"]
        prev_close = df["close"].shift(1)
        tr = pd.concat(
            [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
            axis=1,
        ).max(axis=1)
        return tr.rolling(self.period).mean()


@dataclass
class MomentumFeature(Feature):
    """Price momentum (rate of change)."""

    period: int = 10
    column: str = "close"
    name: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            self.name = f"mom_{self.period}"

    def compute(self, df: pd.DataFrame) -> pd.Series:
        return df[self.column].pct_change(self.period)


@dataclass
class VolatilityFeature(Feature):
    """Rolling volatility (annualized)."""

    period: int = 20
    name: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            self.name = f"vol_{self.period}"

    def compute(self, df: pd.DataFrame) -> pd.Series:
        returns = df["close"].pct_change()
        return returns.rolling(self.period).std() * np.sqrt(252)


@dataclass
class VolumeRatioFeature(Feature):
    """Volume relative to rolling average."""

    period: int = 20
    name: str = ""

    def __post_init__(self) -> None:
        if not self.name:
            self.name = f"vol_ratio_{self.period}"

    def compute(self, df: pd.DataFrame) -> pd.Series:
        avg_vol = df["volume"].rolling(self.period).mean()
        return df["volume"] / avg_vol.replace(0, np.nan)
