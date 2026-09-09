"""HK quality book: EW basket TSMOM sleeve, inverse-vol inside the sleeve."""

from __future__ import annotations

import math
import statistics

import pandas as pd

from quantit.research.universes import HK_QUALITY
from quantit.strategy.base import CASH_BUFFER, Context, Strategy, rebalance_to_weights
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
    """Risk-on sleeve when basket momentum is positive; otherwise ``risk_off_scale``."""
    if momentum is None or pd.isna(momentum):
        return 0.0
    if float(momentum) > 0:
        return float(invested_on)
    return float(risk_off_scale)


def vol_scale(
    realized: float | None,
    target_vol: float,
    vol_floor: float = 0.05,
    max_leverage: float = 1.5,
) -> float:
    """Scale a sleeve toward ``target_vol`` (vol targeting).

    Returns ``target_vol / realized_vol`` capped at ``max_leverage``, so it
    shrinks the sleeve when realized vol exceeds target and may exceed 1 (fill
    up) when realized vol is below target. In ``sleeve_fraction`` that fill-up
    is bounded by ``invested_strong`` (~95%), so ``max_leverage`` values above
    ``invested_strong / invested_on`` (≈1.06 with the defaults) are inert.

    Unknown/non-finite realized vol leaves the sleeve unchanged. ``+inf``
    realized vol shrinks to zero.
    """
    try:
        target = float(target_vol)
    except (TypeError, ValueError):
        return 1.0
    if not math.isfinite(target) or target <= 0:
        return 1.0
    try:
        floor = float(vol_floor)
    except (TypeError, ValueError):
        floor = 0.05
    if not math.isfinite(floor) or floor <= 0:
        floor = 0.05
    try:
        cap = float(max_leverage)
    except (TypeError, ValueError):
        cap = 1.5
    if not math.isfinite(cap) or cap < 1.0:
        cap = 1.0
    if realized is None:
        return 1.0
    try:
        realized_f = float(realized)
    except (TypeError, ValueError):
        return 1.0
    if math.isnan(realized_f):
        return 1.0
    if realized_f == math.inf:
        return 0.0
    if not math.isfinite(realized_f) or realized_f < 0:
        return 1.0
    denom = max(realized_f, floor, 1e-8)
    return min(cap, target / denom)


def sleeve_fraction(
    momentum: float | None,
    realized: float | None,
    *,
    invested_on: float,
    risk_off_scale: float,
    target_vol: float,
    vol_floor: float = 0.05,
    max_leverage: float = 1.5,
    invested_strong: float = 0.90,
    strong_mom: float = 0.20,
) -> float:
    """Momentum sleeve × vol scale, clipped to the book caps.

    Risk-on (momentum > 0) sits at ``invested_on`` (~90%) and de-risks when
    realized vol exceeds ``target_vol``; vol scale may fill it up to
    ``invested_strong`` (~95%) only when skipped-lookback momentum is at least
    ``strong_mom``. Risk-off (momentum ≤ 0) stays at ``risk_off_scale`` (not
    half-cash) and is never filled up.

    The fill-up is at most ``invested_strong / invested_on`` (≈1.06 with the
    defaults), so ``max_leverage`` values above that are effectively inert.
    """
    base = invested_fraction(
        momentum, invested_on=invested_on, risk_off_scale=risk_off_scale
    )
    scaled = base * vol_scale(
        realized, target_vol, vol_floor, max_leverage=max_leverage
    )
    if momentum is None or pd.isna(momentum) or float(momentum) <= 0:
        return min(base, scaled) if base > 0 else 0.0
    try:
        strong_cap = float(invested_strong)
    except (TypeError, ValueError):
        strong_cap = 0.90
    if not math.isfinite(strong_cap) or strong_cap <= 0:
        strong_cap = float(invested_on)
    strong_cap = max(strong_cap, float(invested_on))
    try:
        hurdle = float(strong_mom)
    except (TypeError, ValueError):
        hurdle = 0.20
    if not math.isfinite(hurdle):
        hurdle = 0.20
    cap = strong_cap if float(momentum) >= hurdle else float(invested_on)
    cap = min(max(cap, 0.0), 1.0)
    return min(cap, scaled)


def basket_vol_series(ohlcv: dict[str, pd.DataFrame], period: int) -> pd.Series:
    """Annualized rolling vol of the equal-weight close index."""
    index = equal_weight_index(ohlcv)
    if index.empty or period <= 0:
        return pd.Series(dtype=float)
    return index.pct_change().rolling(int(period)).std() * math.sqrt(252)


def _asof_number(series: pd.Series | None, asof: pd.Timestamp | None = None) -> float | None:
    """Latest value as of ``asof``. Keeps ``+inf``; NaN becomes None."""
    if series is None or getattr(series, "empty", True):
        return None
    hit = series.iloc[-1] if asof is None else series.asof(pd.Timestamp(asof))
    if hit is None or pd.isna(hit):
        return None
    value = float(hit)
    if math.isnan(value):
        return None
    return value


def _asof_float(series: pd.Series | None, asof: pd.Timestamp | None = None) -> float | None:
    value = _asof_number(series, asof)
    if value is None or not math.isfinite(value):
        return None
    return value


def basket_realized_vol(
    ohlcv: dict[str, pd.DataFrame],
    period: int,
    asof: pd.Timestamp | None = None,
) -> float | None:
    series = basket_vol_series(ohlcv, period)
    return _asof_float(series, asof)


def name_vol_series(ohlcv: dict[str, pd.DataFrame], period: int) -> dict[str, pd.Series]:
    """Annualized rolling vol of each name's close."""
    out: dict[str, pd.Series] = {}
    if period <= 0:
        return out
    for symbol, df in ohlcv.items():
        if df is None or getattr(df, "empty", True) or "close" not in df.columns:
            continue
        out[symbol] = df["close"].astype(float).pct_change().rolling(int(period)).std() * math.sqrt(
            252
        )
    return out


def vols_asof(
    series_map: dict[str, pd.Series],
    names: list[str],
    asof: pd.Timestamp,
) -> dict[str, float | None]:
    return {symbol: _asof_number(series_map.get(symbol), asof) for symbol in names}


def name_realized_vols(
    ohlcv: dict[str, pd.DataFrame],
    period: int,
    asof: pd.Timestamp,
    names: list[str],
) -> dict[str, float | None]:
    return vols_asof(name_vol_series(ohlcv, period), names, asof)


def inv_vol_weights(
    names: list[str],
    vols: dict[str, float | None],
    sleeve: float,
    vol_floor: float = 0.05,
) -> dict[str, float]:
    """Vol-parity weights inside a sleeve.

    Missing/NaN/non-positive vol uses the median of known finite vols (equal
    weights if none are known). ``+inf`` vol is dropped (weight 0) so a
    exploding name is not treated as low-vol.
    """
    try:
        sleeve_f = float(sleeve)
    except (TypeError, ValueError):
        return {}
    if not names or not math.isfinite(sleeve_f) or sleeve_f <= 0:
        return {}
    try:
        floor = float(vol_floor)
    except (TypeError, ValueError):
        floor = 0.05
    if not math.isfinite(floor) or floor <= 0:
        floor = 0.05
    finite: dict[str, float] = {}
    missing: list[str] = []
    for symbol in names:
        raw = vols.get(symbol)
        try:
            vol = float(raw) if raw is not None else float("nan")
        except (TypeError, ValueError):
            vol = float("nan")
        if vol == math.inf:
            continue
        if math.isnan(vol) or not math.isfinite(vol) or vol <= 0:
            missing.append(symbol)
            continue
        finite[symbol] = max(vol, floor)
    if finite:
        fill = float(statistics.median(finite.values()))
        for symbol in missing:
            finite[symbol] = fill
    else:
        if not missing:
            return {}
        share = sleeve_f / len(missing)
        return {symbol: share for symbol in missing}
    inv = {symbol: 1.0 / vol for symbol, vol in finite.items()}
    total = sum(inv.values())
    if total <= 0:
        return {}
    return {symbol: sleeve_f * weight / total for symbol, weight in inv.items()}


def name_momentums(
    ohlcv: dict[str, pd.DataFrame],
    lookback: int,
    skip: int,
    asof: pd.Timestamp,
    names: list[str],
) -> dict[str, float | None]:
    """Per-name skipped-lookback return as of ``asof``."""
    out: dict[str, float | None] = {}
    for symbol in names:
        df = ohlcv.get(symbol)
        if df is None or getattr(df, "empty", True) or "close" not in df.columns:
            out[symbol] = None
            continue
        series = tsmom_momentum(df["close"].astype(float), lookback, skip)
        out[symbol] = _asof_float(series, asof)
    return out


def dual_mom_weights(
    names: list[str],
    momentums: dict[str, float | None],
    vols: dict[str, float | None],
    sleeve: float,
    vol_floor: float = 0.05,
) -> dict[str, float]:
    """Absolute gate (mom > 0) then relative split among winners.

    Relative weights mix skipped-lookback magnitude with inverse-vol. If no
    name has positive momentum, fall back to inverse-vol on the full list
    (risk-off sleeve still needs a split).
    """
    try:
        sleeve_f = float(sleeve)
    except (TypeError, ValueError):
        return {}
    if not names or not math.isfinite(sleeve_f) or sleeve_f <= 0:
        return {}
    winners: list[str] = []
    pos: dict[str, float] = {}
    for symbol in names:
        raw = momentums.get(symbol)
        try:
            mom = float(raw) if raw is not None else float("nan")
        except (TypeError, ValueError):
            continue
        if math.isfinite(mom) and mom > 0:
            winners.append(symbol)
            pos[symbol] = mom
    if not winners:
        return inv_vol_weights(names, vols, sleeve_f, vol_floor)
    mag_total = sum(pos.values())
    mag = {symbol: sleeve_f * pos[symbol] / mag_total for symbol in winners}
    iv = inv_vol_weights(winners, vols, sleeve_f, vol_floor)
    blended: dict[str, float] = {}
    for symbol in winners:
        blended[symbol] = 0.5 * mag.get(symbol, 0.0) + 0.5 * iv.get(symbol, 0.0)
    total = sum(blended.values())
    if total <= 0:
        return iv
    return {symbol: sleeve_f * weight / total for symbol, weight in blended.items()}


def quality_targets_from_vols(
    names: list[str],
    vols: dict[str, float | None],
    sleeve: float,
    *,
    weighting: str = "inv_vol",
    vol_floor: float = 0.05,
    momentums: dict[str, float | None] | None = None,
) -> dict[str, float]:
    if sleeve <= 0 or not names:
        return {}
    mode = (weighting or "inv_vol").strip().lower()
    if mode == "equal":
        n = len(names)
        return {symbol: sleeve / n for symbol in names}
    if mode == "dual_mom":
        return dual_mom_weights(names, momentums or {}, vols, sleeve, vol_floor)
    return inv_vol_weights(names, vols, sleeve, vol_floor)


def quality_name_targets(
    ohlcv: dict[str, pd.DataFrame],
    names: list[str],
    sleeve: float,
    asof: pd.Timestamp,
    *,
    vol_lookback: int,
    vol_floor: float,
    weighting: str = "inv_vol",
    lookback: int = 252,
    skip: int = 21,
) -> dict[str, float]:
    """Sleeve split across ``names`` (inverse-vol by default)."""
    vols = name_realized_vols(ohlcv, vol_lookback, asof, names)
    momentums = None
    if (weighting or "").strip().lower() == "dual_mom":
        momentums = name_momentums(ohlcv, lookback, skip, asof, names)
    return quality_targets_from_vols(
        names,
        vols,
        sleeve,
        weighting=weighting,
        vol_floor=vol_floor,
        momentums=momentums,
    )


def quality_sleeve(
    ohlcv: dict[str, pd.DataFrame],
    *,
    lookback: int,
    skip: int,
    invested_on: float,
    risk_off_scale: float,
    target_vol: float,
    vol_lookback: int,
    vol_floor: float,
    asof: pd.Timestamp,
    max_leverage: float = 1.5,
    invested_strong: float = 0.90,
    strong_mom: float = 0.20,
) -> tuple[float, float | None]:
    """Momentum sleeve × vol scale as of ``asof``. Returns ``(frac, momentum)``."""
    mom = basket_momentum(ohlcv, lookback, skip)
    mom_val: float | None = None
    if not mom.empty:
        hit = mom.asof(pd.Timestamp(asof))
        if hit is not None and not pd.isna(hit):
            mom_val = float(hit)
    realized = basket_realized_vol(ohlcv, vol_lookback, asof)
    return sleeve_fraction(
        mom_val,
        realized,
        invested_on=invested_on,
        risk_off_scale=risk_off_scale,
        target_vol=target_vol,
        vol_floor=vol_floor,
        max_leverage=max_leverage,
        invested_strong=invested_strong,
        strong_mom=strong_mom,
    ), mom_val


class HKQualityBookStrategy(Strategy):
    """HK operating blue chips; one skipped-lookback momentum signal.

    Rebalances each session. Residual stays cash (no Hang Seng TECH ETF
    fallback). Typical book ~90% invested; vol leverage may fill to 95% only
    when basket momentum is strong. Risk-off is not forced to half-cash.
    Dual momentum inside the sleeve unless ``weighting=inv_vol`` or ``equal``.
    No shorting.
    """

    def __init__(
        self,
        lookback: int = 252,
        skip: int = 21,
        risk_off_scale: float = 0.70,
        invested_on: float = 0.90,
        turnover_band: float = 0.02,
        target_vol: float = 0.15,
        vol_lookback: int = 20,
        vol_floor: float = 0.05,
        universe: tuple[str, ...] | None = None,
        weighting: str = "dual_mom",
        max_leverage: float = 1.5,
        invested_strong: float = 0.95,
        strong_mom: float = 0.20,
        cash_buffer: float = CASH_BUFFER,
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
        if invested_strong <= 0 or invested_strong > 1:
            raise ValueError("invested_strong must be in (0, 1]")
        if invested_strong < invested_on:
            invested_strong = invested_on
        if target_vol <= 0:
            raise ValueError("target_vol must be positive")
        if vol_lookback <= 0:
            raise ValueError("vol_lookback must be positive")
        if vol_floor <= 0:
            raise ValueError("vol_floor must be positive")
        if max_leverage < 1:
            raise ValueError("max_leverage must be >= 1")
        if strong_mom < 0:
            raise ValueError("strong_mom must be >= 0")
        if not 0 < cash_buffer <= 1:
            raise ValueError("cash_buffer must be in (0, 1]")
        mode = (weighting or "dual_mom").strip().lower()
        if mode not in {"inv_vol", "equal", "dual_mom"}:
            raise ValueError("weighting must be 'inv_vol', 'equal', or 'dual_mom'")
        self.lookback = lookback
        self.skip = skip
        self.risk_off_scale = float(risk_off_scale)
        self.invested_on = float(invested_on)
        self.turnover_band = turnover_band
        self.target_vol = float(target_vol)
        self.vol_lookback = int(vol_lookback)
        self.vol_floor = float(vol_floor)
        self.weighting = mode
        self.max_leverage = float(max_leverage)
        self.invested_strong = float(invested_strong)
        self.strong_mom = float(strong_mom)
        self.cash_buffer = float(cash_buffer)
        self.universe = tuple(universe) if universe is not None else HK_QUALITY
        self._mom: pd.Series | None = None
        self._vol: pd.Series | None = None
        self._name_vol: dict[str, pd.Series] | None = None

    def on_start(self, context: Context) -> None:
        frames = context.data_map or {context.symbol: context.data}
        self._mom = basket_momentum(frames, self.lookback, self.skip)
        self._vol = basket_vol_series(frames, self.vol_lookback)
        self._name_vol = name_vol_series(frames, self.vol_lookback)
        if self._mom is not None and not self._mom.empty:
            context.indicators["hk_basket_tsmom"] = self._mom
        if self._vol is not None and not self._vol.empty:
            context.indicators["hk_basket_vol"] = self._vol

    def on_bar(self, context: Context, bar: pd.Series) -> None:
        if context.current_date is None or self._mom is None or self._mom.empty:
            return
        ts = pd.Timestamp(context.current_date)
        need = self.lookback + 1
        if len(self._mom.loc[:ts]) < need:
            return
        asof = self._mom.asof(ts)
        if asof is None or (isinstance(asof, float) and pd.isna(asof)):
            return
        realized: float | None = None
        if self._vol is not None and not self._vol.empty:
            vol_hit = self._vol.asof(ts)
            if vol_hit is not None and not pd.isna(vol_hit):
                realized = float(vol_hit)
        frac = sleeve_fraction(
            float(asof),
            realized,
            invested_on=self.invested_on,
            risk_off_scale=self.risk_off_scale,
            target_vol=self.target_vol,
            vol_floor=self.vol_floor,
            max_leverage=self.max_leverage,
            invested_strong=self.invested_strong,
            strong_mom=self.strong_mom,
        )
        quoted = [
            s
            for s in self.universe
            if s in (context.prices or {}) and float(context.prices[s]) > 0
        ]
        if not quoted and frac > 0:
            quoted = [s for s, px in (context.prices or {}).items() if px and px > 0]
        vols = vols_asof(self._name_vol or {}, quoted, ts)
        momentums = None
        if self.weighting == "dual_mom":
            momentums = name_momentums(
                context.data_map or {context.symbol: context.data},
                self.lookback,
                self.skip,
                ts,
                quoted,
            )
        target = quality_targets_from_vols(
            quoted,
            vols,
            frac,
            weighting=self.weighting,
            vol_floor=self.vol_floor,
            momentums=momentums,
        )
        self._rebalance(context, target)

    def _rebalance(self, context: Context, target_weights: dict[str, float]) -> None:
        rebalance_to_weights(
            context,
            target_weights,
            turnover_band=self.turnover_band,
            cash_buffer=self.cash_buffer,
        )
