"""Equal-weight HK quality book with a single basket TSMOM overlay."""

from __future__ import annotations

import pandas as pd

from quantit.research.universes import HK_QUALITY
from quantit.strategy.base import Context, Strategy
from quantit.strategy.regime import is_month_end
from quantit.strategy.tsmom import tsmom_momentum


def equal_weight_index(ohlcv: dict[str, pd.DataFrame]) -> pd.Series:
    """Daily equal-weight total-return index of names that have a close."""
    closes: list[pd.Series] = []
    for df in ohlcv.values():
        if df is None or getattr(df, "empty", True) or "close" not in df.columns:
            continue
        closes.append(df["close"].astype(float))
    if not closes:
        return pd.Series(dtype=float)
    panel = pd.concat(closes, axis=1).sort_index()
    ew_ret = panel.pct_change().mean(axis=1, skipna=True)
    return (1.0 + ew_ret.fillna(0.0)).cumprod()


def basket_momentum(ohlcv: dict[str, pd.DataFrame], lookback: int, skip: int) -> pd.Series:
    index = equal_weight_index(ohlcv)
    if index.empty:
        return pd.Series(dtype=float)
    return tsmom_momentum(index, lookback, skip)


def invested_fraction(
    momentum: float | None,
    *,
    invested_on: float,
    risk_off_scale: float,
) -> float:
    """Full sleeve when basket momentum is positive; otherwise ``risk_off_scale``."""
    if momentum is None or pd.isna(momentum):
        return 0.0
    if float(momentum) > 0:
        return float(invested_on)
    return float(risk_off_scale)


class HKQualityBookStrategy(Strategy):
    """Equal-weight HK operating blue chips; one skipped-lookback momentum signal.

    Rebalances on the last session of each month. Residual weight stays cash
    (no Hang Seng TECH ETF fallback). No shorting.
    """

    def __init__(
        self,
        lookback: int = 252,
        skip: int = 21,
        risk_off_scale: float = 0.5,
        invested_on: float = 0.95,
        turnover_band: float = 0.02,
        universe: tuple[str, ...] | None = None,
    ) -> None:
        if lookback <= 0:
            raise ValueError("lookback must be positive")
        if skip < 0:
            raise ValueError("skip must be >= 0")
        if skip >= lookback:
            raise ValueError("skip must be less than lookback")
        if risk_off_scale < 0 or risk_off_scale > 1:
            raise ValueError("risk_off_scale must be in [0, 1]")
        if invested_on <= 0 or invested_on > 1:
            raise ValueError("invested_on must be in (0, 1]")
        self.lookback = lookback
        self.skip = skip
        self.risk_off_scale = float(risk_off_scale)
        self.invested_on = float(invested_on)
        self.turnover_band = turnover_band
        self.universe = tuple(universe) if universe is not None else HK_QUALITY
        self._mom: pd.Series | None = None
        self._dates: pd.DatetimeIndex | None = None

    def on_start(self, context: Context) -> None:
        frames = context.data_map or {context.symbol: context.data}
        self._mom = basket_momentum(frames, self.lookback, self.skip)
        calendar = None
        for df in frames.values():
            if df is None or getattr(df, "empty", True):
                continue
            calendar = df.index if calendar is None else calendar.union(df.index)
        self._dates = pd.DatetimeIndex(calendar).sort_values().normalize() if calendar is not None else None
        if self._mom is not None and not self._mom.empty:
            context.indicators["hk_basket_tsmom"] = self._mom

    def on_bar(self, context: Context, bar: pd.Series) -> None:
        if context.current_date is None or self._dates is None or self._mom is None or self._mom.empty:
            return
        ts = pd.Timestamp(context.current_date)
        if not is_month_end(self._dates, ts):
            return
        need = self.lookback + 1
        if len(self._mom.loc[:ts]) < need:
            return
        asof = self._mom.asof(ts)
        if asof is None or (isinstance(asof, float) and pd.isna(asof)):
            return
        frac = invested_fraction(
            float(asof),
            invested_on=self.invested_on,
            risk_off_scale=self.risk_off_scale,
        )
        quoted = [
            s
            for s in self.universe
            if s in (context.prices or {}) and float(context.prices[s]) > 0
        ]
        if not quoted and frac > 0:
            quoted = [s for s, px in (context.prices or {}).items() if px and px > 0]
        n = len(quoted)
        target = {s: (frac / n) for s in quoted} if n and frac > 0 else {}
        self._rebalance(context, target)

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
