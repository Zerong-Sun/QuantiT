"""Black-Scholes ATM calls and a levered quality-book overlay (research only).

No listed chain is required: premiums and expiries are model-priced from
spot + realized vol. Contracts with DTE below ``min_dte`` are never held
(no 末日/0DTE). Two-thirds of target delta goes to calls first; one-third
to cash equity. Multiple stock and option tickets may fill the same session.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from quantit.analysis.metrics import compute_metrics
from quantit.engine.backtester import BacktestResult
from quantit.engine.portfolio import Portfolio
from quantit.strategy.hk_book import (
    basket_momentum,
    basket_vol_series,
    name_vol_series,
    quality_targets_from_vols,
    sleeve_fraction,
    vols_asof,
)
from quantit.utils.config import get_config


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_call(
    spot: float,
    strike: float,
    dte: int,
    vol: float,
    rate: float = 0.03,
) -> tuple[float, float]:
    """Return ``(premium per share, delta)``. ``dte`` in calendar days."""
    s = max(float(spot), 1e-8)
    k = max(float(strike), 1e-8)
    t = max(int(dte), 0) / 365.0
    sig = max(float(vol), 1e-6)
    if t <= 1e-8:
        intrinsic = max(s - k, 0.0)
        return intrinsic, 1.0 if s > k else 0.0
    sqrt_t = math.sqrt(t)
    d1 = (math.log(s / k) + (rate + 0.5 * sig * sig) * t) / (sig * sqrt_t)
    d2 = d1 - sig * sqrt_t
    premium = s * _norm_cdf(d1) - k * math.exp(-rate * t) * _norm_cdf(d2)
    return max(premium, 0.0), float(_norm_cdf(d1))


def third_fridays(start: date, end: date, extra_days: int = 400) -> list[date]:
    """Monthly standard expiries (third Friday), including a buffer after ``end``."""
    out: list[date] = []
    y, m = start.year, start.month
    stop = end + timedelta(days=extra_days)
    while date(y, m, 1) <= date(stop.year, stop.month, 1):
        d = date(y, m, 15)
        while d.weekday() != 4:
            d += timedelta(days=1)
        if d >= start:
            out.append(d)
        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1
    return out


def pick_standard_expiry(
    asof: date,
    expiries: list[date],
    min_dte: int = 21,
    max_dte: int = 90,
    prefer: str = "nearest",
) -> date | None:
    """Pick a listed-style expiry. ``prefer='longest'`` reduces roll/theta."""
    future: list[tuple[int, date]] = []
    for exp in expiries:
        dte = (exp - asof).days
        if dte >= 0:
            future.append((dte, exp))
    if not future:
        return None
    eligible = [row for row in future if row[0] >= min_dte]
    if not eligible:
        return None
    in_band = [row for row in eligible if row[0] <= max_dte]
    pool = in_band or eligible
    if prefer == "longest":
        pool.sort(key=lambda row: row[0], reverse=True)
    else:
        pool.sort(key=lambda row: row[0])
    return pool[0][1]


def atm_strike(spot: float) -> float:
    px = max(float(spot), 0.01)
    if px >= 50:
        step = 5.0 if px >= 200 else 1.0
    else:
        step = 0.5
    return round(px / step) * step


def occ_tag(underlying: str, expiry: date, strike: float) -> str:
    safe = underlying.replace(".", "").replace(" ", "")[:12]
    return f"{safe}{expiry.strftime('%y%m%d')}C{int(round(strike * 1000)):08d}"


@dataclass
class CallLot:
    underlying: str
    expiry: date
    strike: float
    quantity: int
    tag: str


@dataclass
class OverlayConfig:
    lookback: int = 252
    skip: int = 21
    target_vol: float = 0.15
    vol_lookback: int = 20
    vol_floor: float = 0.05
    invested_on: float = 0.80
    invested_strong: float = 0.90
    strong_mom: float = 0.20
    max_leverage: float = 1.5
    risk_off_scale: float = 0.70
    target_exposure: float = 0.95
    spot_share: float = 1.0 / 3.0
    call_share: float = 2.0 / 3.0
    min_dte: int = 21
    max_dte: int = 90
    expiry_prefer: str = "nearest"
    moneyness: float = 1.0
    apply_momentum: bool = True
    sticky_strikes: bool = True
    qty_band: float = 0.10
    vol_iv_floor: float = 0.12
    commission_rate: float = 0.001
    slippage_rate: float = 0.0005


def _apply_buy(port: Portfolio, symbol: str, qty: int, price: float, slip: float, comm: float) -> None:
    if qty <= 0 or price <= 0:
        return
    fill = price * (1 + slip)
    cost = fill * qty * (1 + comm)
    if cost > port.cash:
        qty = int(port.cash / (fill * (1 + comm)))
        if qty <= 0:
            return
        cost = fill * qty * (1 + comm)
    port.buy(symbol, qty, fill, cost - fill * qty)


def _apply_sell(port: Portfolio, symbol: str, qty: int, price: float, slip: float, comm: float) -> None:
    held = port.get_position(symbol).quantity
    qty = min(int(qty), held)
    if qty <= 0 or price <= 0:
        return
    fill = max(price * (1 - slip), 0.0)
    proceeds = fill * qty
    fee = proceeds * comm
    port.sell(symbol, qty, fill, fee)


def run_levered_call_book(
    ohlcv: dict[str, pd.DataFrame],
    *,
    initial_cash: float,
    cfg: OverlayConfig | None = None,
    rate: float | None = None,
) -> BacktestResult:
    """Daily overlay: 1/3 spot + 2/3 call delta, roll before ``min_dte``."""
    cfg = cfg or OverlayConfig()
    rf = get_config().risk_free_rate if rate is None else float(rate)
    names = [s for s, df in ohlcv.items() if df is not None and not df.empty and "close" in df.columns]
    if not names:
        raise ValueError("empty book")
    calendar = None
    for df in ohlcv.values():
        if df is None or df.empty:
            continue
        calendar = df.index if calendar is None else calendar.union(df.index)
    dates = pd.DatetimeIndex(calendar).sort_values().unique()
    start_d = pd.Timestamp(dates[0]).date()
    end_d = pd.Timestamp(dates[-1]).date()
    expiries = third_fridays(start_d, end_d, extra_days=max(400, int(cfg.max_dte) + 40))

    mom = basket_momentum(ohlcv, cfg.lookback, cfg.skip)
    bvol = basket_vol_series(ohlcv, cfg.vol_lookback)
    nvol = name_vol_series(ohlcv, cfg.vol_lookback)

    port = Portfolio(initial_cash=float(initial_cash))
    lots: dict[str, CallLot] = {}

    def mark_prices(ts: pd.Timestamp, spots: dict[str, float]) -> dict[str, float]:
        px = dict(spots)
        asof = pd.Timestamp(ts).date()
        for tag, lot in lots.items():
            spot = spots.get(lot.underlying)
            if spot is None:
                continue
            dte = (lot.expiry - asof).days
            iv = _iv(nvol, lot.underlying, ts, cfg)
            prem, _ = bs_call(spot, lot.strike, dte, iv, rf)
            px[tag] = prem
        return px

    for ts in dates:
        spots: dict[str, float] = {}
        for sym in names:
            df = ohlcv[sym]
            if ts not in df.index:
                continue
            close = float(df.loc[ts, "close"])
            if close > 0:
                spots[sym] = close
        if not spots:
            continue
        asof = pd.Timestamp(ts).date()
        prices = mark_prices(ts, spots)
        port.record(pd.Timestamp(ts).to_pydatetime(), prices)
        if cfg.apply_momentum:
            if mom.empty:
                continue
            hit = mom.asof(ts)
            if hit is None or pd.isna(hit):
                continue
            if len(mom.loc[:ts]) < cfg.lookback + 1:
                continue
            realized = None
            if not bvol.empty:
                vh = bvol.asof(ts)
                if vh is not None and not pd.isna(vh):
                    realized = float(vh)
            sleeve = sleeve_fraction(
                float(hit),
                realized,
                invested_on=cfg.invested_on,
                risk_off_scale=cfg.risk_off_scale,
                target_vol=cfg.target_vol,
                vol_floor=cfg.vol_floor,
                max_leverage=cfg.max_leverage,
                invested_strong=cfg.invested_strong,
                strong_mom=cfg.strong_mom,
            )
            exposure = (
                max(float(sleeve), float(cfg.target_exposure))
                if float(hit) > 0
                else float(sleeve)
            )
        else:
            loc = int(dates.searchsorted(ts))
            if loc < cfg.vol_lookback + 1:
                continue
            exposure = float(cfg.target_exposure)
        quoted = [s for s in names if s in spots]
        vols = vols_asof(nvol, quoted, ts)
        weights = quality_targets_from_vols(
            quoted, vols, 1.0, weighting="inv_vol", vol_floor=cfg.vol_floor
        )
        if not weights:
            continue
        equity = port.equity(prices)
        if equity <= 0:
            continue

        # 1) Flatten 末日 and expired lots (multiple sells this session).
        for tag, lot in list(lots.items()):
            dte = (lot.expiry - asof).days
            if dte >= cfg.min_dte and lot.underlying in spots:
                continue
            prem = prices.get(tag, 0.0)
            if dte <= 0:
                prem = max(spots.get(lot.underlying, 0.0) - lot.strike, 0.0)
            _apply_sell(port, tag, lot.quantity, prem, cfg.slippage_rate, cfg.commission_rate)
            lots.pop(tag, None)

        prices = mark_prices(ts, spots)
        equity = port.equity(prices)

        # 2) Calls first (2/3 of target delta).
        call_budget = equity * exposure * cfg.call_share
        for sym, w in weights.items():
            spot = spots[sym]
            held_lot = next((lot for lot in lots.values() if lot.underlying == sym), None)
            if cfg.sticky_strikes and held_lot is not None:
                expiry, strike, tag = held_lot.expiry, held_lot.strike, held_lot.tag
            else:
                expiry = pick_standard_expiry(
                    asof, expiries, cfg.min_dte, cfg.max_dte, prefer=cfg.expiry_prefer
                )
                if expiry is None:
                    continue
                strike = atm_strike(spot * float(cfg.moneyness))
                tag = occ_tag(sym, expiry, strike)
                for other_tag, other in list(lots.items()):
                    if other.underlying == sym and other.tag != tag:
                        op = prices.get(other.tag) or mark_prices(ts, spots).get(other.tag, 0.0)
                        _apply_sell(
                            port, other.tag, other.quantity, op, cfg.slippage_rate, cfg.commission_rate
                        )
                        lots.pop(other.tag, None)
            dte = (expiry - asof).days
            if dte < cfg.min_dte:
                continue
            iv = _iv(nvol, sym, ts, cfg)
            prem, delta = bs_call(spot, strike, dte, iv, rf)
            if prem <= 0 or delta <= 1e-6:
                continue
            target_delta_notional = call_budget * w
            target_qty = int(target_delta_notional / (delta * spot))
            current_qty = lots[tag].quantity if tag in lots else 0
            if cfg.sticky_strikes and current_qty > 0:
                continue
            diff = target_qty - current_qty
            band = max(1, int(abs(target_qty) * float(cfg.qty_band)))
            if current_qty > 0 and abs(diff) < band:
                continue
            if diff > 0:
                _apply_buy(port, tag, diff, prem, cfg.slippage_rate, cfg.commission_rate)
                filled = port.get_position(tag).quantity
                lots[tag] = CallLot(sym, expiry, strike, filled, tag)
            elif diff < 0 and tag in lots:
                _apply_sell(port, tag, -diff, prem, cfg.slippage_rate, cfg.commission_rate)
                left = port.get_position(tag).quantity
                if left <= 0:
                    lots.pop(tag, None)
                else:
                    lots[tag] = CallLot(sym, expiry, strike, left, tag)

        prices = mark_prices(ts, spots)
        equity = port.equity(prices)

        # 3) Residual third in cash equity (several stock tickets).
        spot_budget = equity * exposure * cfg.spot_share
        for sym, w in weights.items():
            spot = spots[sym]
            target_qty = int(spot_budget * w / spot)
            current = port.get_position(sym).quantity
            diff = target_qty - current
            if diff > 0:
                _apply_buy(port, sym, diff, spot, cfg.slippage_rate, cfg.commission_rate)
            elif diff < 0:
                _apply_sell(port, sym, -diff, spot, cfg.slippage_rate, cfg.commission_rate)

        # Drop empty stock lots from tracking; options already in ``lots``.

    equity_curve = port.equity_curve()
    result = BacktestResult(
        equity_curve=equity_curve,
        trades=[],
        portfolio=port,
        symbol="LEVERED-CALLS",
        start=pd.Timestamp(dates[0]).to_pydatetime(),
        end=pd.Timestamp(dates[-1]).to_pydatetime(),
    )
    if not equity_curve.empty:
        compute_metrics(result)
    return result


def _iv(nvol: dict[str, pd.Series], symbol: str, ts: pd.Timestamp, cfg: OverlayConfig) -> float:
    series = nvol.get(symbol)
    if series is None or series.empty:
        return cfg.vol_iv_floor
    hit = series.asof(ts)
    if hit is None or pd.isna(hit):
        return cfg.vol_iv_floor
    return max(float(hit), cfg.vol_iv_floor)
