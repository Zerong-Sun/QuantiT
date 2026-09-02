"""Monthly theme-rotation strategy (long-horizon, multi-asset)."""

from __future__ import annotations

import pandas as pd

from quantit.features.regime import scores_to_theme_weights
from quantit.markets.hk import HSTECH_ETF, HSTECH_THEMES
from quantit.strategy.base import Context, Strategy


def is_month_end(dates: pd.DatetimeIndex, when: pd.Timestamp) -> bool:
    """True if ``when`` is the last session in its month on ``dates``."""
    ts = pd.Timestamp(when).normalize()
    idx = pd.DatetimeIndex(dates).normalize()
    loc = idx.get_indexer([ts])[0]
    if loc < 0:
        return False
    if loc >= len(idx) - 1:
        return True
    nxt = pd.Timestamp(idx[loc + 1])
    return ts.month != nxt.month or ts.year != nxt.year


def feasible_hk_weights(
    target: dict[str, float],
    prices: dict[str, float],
    equity: float,
    lot_sizes: dict[str, int] | None = None,
    fallback: str = HSTECH_ETF,
) -> dict[str, float]:
    """Drop names that cannot buy one lot; send residual weight to ``fallback`` or cash."""
    lots = lot_sizes or {}
    kept: dict[str, float] = {}
    residual = 0.0
    for symbol, weight in target.items():
        if weight <= 0:
            continue
        px = prices.get(symbol)
        lot = lots.get(symbol, 1) or 1
        if px is None or px <= 0 or equity * weight < lot * px:
            residual += weight
            continue
        kept[symbol] = kept.get(symbol, 0.0) + weight
    if residual > 0:
        fb_px = prices.get(fallback)
        fb_lot = lots.get(fallback, 1) or 1
        if fallback and fb_px is not None and fb_px > 0 and equity * residual >= fb_lot * fb_px:
            kept[fallback] = kept.get(fallback, 0.0) + residual
    return kept


class ThemeRotationStrategy(Strategy):
    """Allocate to Hang Seng TECH themes from precomputed regime scores.

    Rebalances on the last session of each month. Theme weights are spread
    equally across members that have a quote that day. Remainder is cash.
    """

    def __init__(
        self,
        scores: pd.DataFrame,
        themes: dict[str, list[str]] | None = None,
        cash_threshold: float = -0.5,
        risk_off_invested: float = 0.40,
        equal_weight_band: float = 0.25,
        turnover_band: float = 0.02,
    ) -> None:
        self.scores = scores.sort_index()
        self.themes = themes or HSTECH_THEMES
        self.cash_threshold = cash_threshold
        self.risk_off_invested = risk_off_invested
        self.equal_weight_band = equal_weight_band
        self.turnover_band = turnover_band
        self._dates: pd.DatetimeIndex | None = None

    def on_start(self, context: Context) -> None:
        if context.data_map:
            calendar = None
            for df in context.data_map.values():
                calendar = df.index if calendar is None else calendar.union(df.index)
            self._dates = pd.DatetimeIndex(calendar).sort_values().normalize()
        else:
            self._dates = pd.DatetimeIndex(context.data.index).normalize()

    def on_bar(self, context: Context, bar: pd.Series) -> None:
        if context.current_date is None or self._dates is None:
            return
        ts = pd.Timestamp(context.current_date)
        if not is_month_end(self._dates, ts):
            return
        row = self.scores.asof(ts)
        if row is None or not isinstance(row, pd.Series) or row.isna().all():
            return
        theme_scores = {k: float(v) for k, v in row.items() if k in self.themes}
        if not theme_scores:
            return
        theme_w = scores_to_theme_weights(
            theme_scores,
            cash_threshold=self.cash_threshold,
            risk_off_invested=self.risk_off_invested,
            equal_weight_band=self.equal_weight_band,
        )
        target = self._expand_to_symbols(theme_w, context.prices)
        self._rebalance(context, target)

    def _expand_to_symbols(
        self,
        theme_weights: dict[str, float],
        prices: dict[str, float],
    ) -> dict[str, float]:
        target: dict[str, float] = {}
        for theme, weight in theme_weights.items():
            members = [s for s in self.themes.get(theme, []) if s in prices and prices[s] > 0]
            if not members or weight <= 0:
                continue
            each = weight / len(members)
            for symbol in members:
                target[symbol] = target.get(symbol, 0.0) + each
        return target

    def _rebalance(self, context: Context, target_weights: dict[str, float]) -> None:
        prices = context.prices
        if not prices:
            return
        equity = context.portfolio.equity(prices)
        if equity <= 0:
            return

        sells: list[tuple[str, int]] = []
        buys: list[tuple[str, int]] = []
        held = {s for s, p in context.portfolio.positions.items() if p.quantity > 0}
        for symbol in set(prices) | held:
            px = prices.get(symbol)
            if px is None or px <= 0:
                continue
            target_qty = int(equity * target_weights.get(symbol, 0.0) / px)
            current = context.position_of(symbol)
            diff = target_qty - current
            if diff == 0:
                continue
            if current > 0 and target_qty > 0 and abs(diff) / current <= self.turnover_band:
                continue
            if diff < 0:
                sells.append((symbol, min(-diff, current)))
            else:
                buys.append((symbol, diff))

        for symbol, qty in sells:
            if qty > 0:
                context.sell(qty, symbol=symbol)

        estimated_cash = context.portfolio.cash
        for symbol, qty in sells:
            estimated_cash += qty * prices.get(symbol, 0.0) * (1 - 0.002)

        buy_notional = sum(qty * prices[s] for s, qty in buys if s in prices)
        if buy_notional > estimated_cash * 0.98 and buy_notional > 0:
            scale = (estimated_cash * 0.98) / buy_notional
            buys = [(s, int(qty * scale)) for s, qty in buys]

        for symbol, qty in buys:
            if qty > 0:
                context.buy(qty, symbol=symbol)
