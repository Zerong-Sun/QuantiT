"""Strategy factories and default grids for research."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import pandas as pd

from quantit.markets.cn import CN_ETF_THEMES
from quantit.strategy.base import Strategy
from quantit.strategy.regime import ThemeRotationStrategy
from quantit.strategy.technical import MACrossoverStrategy, RSIMeanReversionStrategy
from quantit.strategy.tsmom import TSMOMStrategy
from quantit.strategy.us_book import USBookStrategy


@dataclass
class StrategySpec:
    strategy_id: str
    builder: Callable[..., Strategy]
    grid: list[dict[str, Any]]
    promote: bool = False
    kind: str = "single"
    extra_keys: tuple[str, ...] = ()


def _tsmom_grid() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for lookback in (126, 252):
        for skip in (0, 21):
            if skip >= lookback:
                continue
            for target_vol in (0.10, 0.15):
                rows.append({"lookback": lookback, "skip": skip, "target_vol": target_vol})
    return rows


def _us_book_grid() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for fast in (5, 10, 20):
        for slow in (20, 50, 100):
            if fast >= slow:
                continue
            for buy_th in (25, 30):
                for sell_th in (70, 75):
                    rows.append(
                        {
                            "fast_period": fast,
                            "slow_period": slow,
                            "period": 14,
                            "buy_threshold": buy_th,
                            "sell_threshold": sell_th,
                        }
                    )
    return rows


def _theme_grid() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for cash_threshold in (-1.0, -0.5, 0.0):
        for risk_off in (0.3, 0.4, 0.5):
            rows.append({"cash_threshold": cash_threshold, "risk_off_invested": risk_off})
    return rows


def _ma_grid() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for fast in (5, 10, 20):
        for slow in (20, 50, 100):
            if fast < slow:
                rows.append({"fast_period": fast, "slow_period": slow})
    return rows


def _rsi_grid() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for buy_th in (25, 30):
        for sell_th in (70, 75):
            rows.append({"period": 14, "buy_threshold": buy_th, "sell_threshold": sell_th})
    return rows


def _make_theme(scores: pd.DataFrame, **params: Any) -> ThemeRotationStrategy:
    return ThemeRotationStrategy(scores=scores, **params)


def _make_cn_etf(scores: pd.DataFrame, **params: Any) -> ThemeRotationStrategy:
    return ThemeRotationStrategy(scores=scores, themes=CN_ETF_THEMES, **params)


SPECS: dict[str, StrategySpec] = {
    "tsmom": StrategySpec("tsmom", TSMOMStrategy, _tsmom_grid(), promote=True),
    "us_book": StrategySpec("us_book", USBookStrategy, _us_book_grid(), promote=False),
    "ma_crossover": StrategySpec("ma_crossover", MACrossoverStrategy, _ma_grid(), promote=False),
    "rsi_mean_reversion": StrategySpec(
        "rsi_mean_reversion", RSIMeanReversionStrategy, _rsi_grid(), promote=False
    ),
    "theme_rotation": StrategySpec(
        "theme_rotation",
        _make_theme,
        _theme_grid(),
        promote=False,
        kind="multi",
        extra_keys=("scores",),
    ),
    "cn_etf_rotation": StrategySpec(
        "cn_etf_rotation",
        _make_cn_etf,
        _theme_grid(),
        promote=False,
        kind="multi",
        extra_keys=("scores",),
    ),
}


def get_spec(strategy_id: str) -> StrategySpec:
    spec = SPECS.get(strategy_id)
    if spec is None:
        raise KeyError(f"Unknown research strategy {strategy_id!r}")
    return spec
