"""Alphalens-style IC on a single basket TSMOM signal.

Paper pytest stays free of ``alphalens-reloaded`` (closeloop extra only).
The signal is the skipped-lookback return of the equal-weight close index;
forward returns are the next ``horizon``-day EW index returns.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from quantit.data.cache import DataCache
from quantit.research.params import strategy_params
from quantit.research.universes import CN_QUALITY, HK_QUALITY, US_QUALITY, YAHOO_ALIASES
from quantit.strategy.cn_book import CNQualityBookStrategy
from quantit.strategy.hk_book import HKQualityBookStrategy, equal_weight_index
from quantit.strategy.tsmom import TSMOMStrategy, tsmom_momentum


def spearman_ic(signal: pd.Series, forward: pd.Series) -> float:
    aligned = pd.concat({"signal": signal, "fwd": forward}, axis=1).dropna()
    if len(aligned) < 3:
        return float("nan")
    rx = aligned["signal"].rank(method="average")
    ry = aligned["fwd"].rank(method="average")
    if rx.nunique() < 2 or ry.nunique() < 2:
        return float("nan")
    value = rx.corr(ry, method="pearson")
    if value is None or pd.isna(value):
        return float("nan")
    return float(value)


def quantile_mean_returns(
    signal: pd.Series, forward: pd.Series, n: int = 5
) -> dict[str, float]:
    aligned = pd.concat({"signal": signal, "fwd": forward}, axis=1).dropna()
    if aligned.empty or aligned["signal"].nunique() < 2:
        return {}
    bins = min(int(n), int(aligned["signal"].nunique()))
    if bins < 2:
        return {}
    try:
        q = pd.qcut(aligned["signal"], bins, labels=False, duplicates="drop")
    except ValueError:
        return {}
    means = aligned["fwd"].groupby(q).mean()
    return {str(int(k)): float(v) for k, v in means.items() if pd.notna(v)}


def _empty_report(**extra: Any) -> dict[str, Any]:
    out: dict[str, Any] = {
        "n": 0,
        "ic": float("nan"),
        "on_mean": float("nan"),
        "off_mean": float("nan"),
        "on_share": float("nan"),
        "off_share": float("nan"),
        "quantile_spread": float("nan"),
        "quantiles": {},
    }
    out.update(extra)
    return out


def diagnose_basket_tsmom(
    ohlcv: dict[str, pd.DataFrame],
    lookback: int,
    skip: int,
    horizon: int = 1,
) -> dict[str, Any]:
    """Rank IC, on/off day means, and quantile spread for basket TSMOM."""
    extra = {
        "lookback": int(lookback),
        "skip": int(skip),
        "horizon": int(horizon),
        "n_names": int(len(ohlcv)),
    }
    index = equal_weight_index(ohlcv)
    if index.empty or lookback <= 0 or horizon <= 0 or skip < 0 or skip >= lookback:
        return _empty_report(**extra)
    try:
        signal = tsmom_momentum(index, lookback, skip)
    except ValueError:
        return _empty_report(**extra)
    forward = index.pct_change(int(horizon)).shift(-int(horizon))
    aligned = pd.concat({"signal": signal, "fwd": forward}, axis=1).dropna()
    n = int(len(aligned))
    if n == 0:
        return _empty_report(**extra)
    on = aligned["signal"] > 0
    on_fwd = aligned.loc[on, "fwd"]
    off_fwd = aligned.loc[~on, "fwd"]
    qmeans = quantile_mean_returns(aligned["signal"], aligned["fwd"])
    spread = float("nan")
    if qmeans:
        keys = sorted(int(k) for k in qmeans)
        spread = qmeans[str(keys[-1])] - qmeans[str(keys[0])]
    report = _empty_report(**extra)
    report.update(
        {
            "n": n,
            "ic": spearman_ic(aligned["signal"], aligned["fwd"]),
            "on_mean": float(on_fwd.mean()) if len(on_fwd) else float("nan"),
            "off_mean": float(off_fwd.mean()) if len(off_fwd) else float("nan"),
            "on_share": float(on.mean()),
            "off_share": float((~on).mean()),
            "quantile_spread": spread,
            "quantiles": qmeans,
        }
    )
    return report


def _naive_index(index: pd.Index) -> pd.DatetimeIndex:
    idx = pd.DatetimeIndex(pd.to_datetime(index))
    if idx.tz is not None:
        idx = idx.tz_convert("UTC").tz_localize(None)
    return idx.normalize()


def load_cached_book(
    symbols: tuple[str, ...] | list[str],
    start: str,
    end: str,
    cache: DataCache | None = None,
) -> dict[str, pd.DataFrame]:
    store = cache or DataCache()
    start_ts = pd.Timestamp(start).normalize()
    end_ts = pd.Timestamp(end).normalize()
    out: dict[str, pd.DataFrame] = {}
    for symbol in symbols:
        fetch = YAHOO_ALIASES.get(symbol, symbol)
        frame = store.get(fetch, "1d")
        if frame is None or frame.empty or "close" not in frame.columns:
            continue
        sliced = frame.copy()
        sliced.index = _naive_index(sliced.index)
        sliced = sliced.loc[start_ts:end_ts]
        if sliced.empty:
            continue
        out[symbol] = sliced
    return out


def _cfg_int(value: object, default: int) -> int:
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return number


def diagnose_cached_quality(
    market: str,
    start: str = "2012-01-01",
    end: str = "2024-12-31",
    *,
    lookback: int | None = None,
    skip: int | None = None,
    horizon: int = 1,
    cache: DataCache | None = None,
) -> dict[str, Any]:
    """Run the IC diagnostic on cached bars for one quality universe.

    Lookback/skip default to live YAML, then the strategy constructor.
    """
    key = market.strip().lower()
    if key == "hk":
        names = HK_QUALITY
        defaults = HKQualityBookStrategy()
        cfg = strategy_params("hk_quality_book")
    elif key == "us":
        names = US_QUALITY
        defaults = TSMOMStrategy()
        cfg = strategy_params("tsmom")
    elif key == "cn":
        names = CN_QUALITY
        defaults = CNQualityBookStrategy()
        cfg = strategy_params("cn_quality_book")
    else:
        raise ValueError(f"unknown quality market {market!r}")
    lb = defaults.lookback if lookback is None else lookback
    sk = defaults.skip if skip is None else skip
    if lookback is None:
        parsed = _cfg_int(cfg.get("lookback"), defaults.lookback)
        if parsed > 0:
            lb = parsed
    if skip is None:
        parsed = _cfg_int(cfg.get("skip"), defaults.skip)
        if parsed >= 0:
            sk = parsed
    book = load_cached_book(names, start, end, cache=cache)
    report = diagnose_basket_tsmom(book, lb, sk, horizon=horizon)
    report["market"] = key
    report["missing"] = [s for s in names if s not in book]
    return report


def main() -> None:
    import json

    rows = [diagnose_cached_quality(market) for market in ("hk", "us", "cn")]
    slim = [
        {
            "market": r["market"],
            "n": r["n"],
            "n_names": r["n_names"],
            "missing": r["missing"],
            "lookback": r["lookback"],
            "skip": r["skip"],
            "ic": r["ic"],
            "on_mean": r["on_mean"],
            "off_mean": r["off_mean"],
            "on_share": r["on_share"],
            "quantile_spread": r["quantile_spread"],
        }
        for r in rows
    ]
    print(json.dumps(slim, indent=2, default=str))


if __name__ == "__main__":
    main()
