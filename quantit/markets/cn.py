"""Onshore A-share market profile, ETF themes, and AkShare-backed adapter."""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from quantit.data.provider import DataProvider
from quantit.markets.adapter import MarketAdapter
from quantit.markets.base import MarketProfile

CN_PROFILE = MarketProfile(
    name="cn",
    currency="CNY",
    trading_days_per_year=242,
    commission_rate=0.0003,
    stamp_duty_rate=0.0005,
    slippage_rate=0.0005,
    lot_size_note="A-shares trade in lots of 100; T+1 settlement. Onshore ETFs are stamp-duty exempt.",
)

# Residual vehicle when a sleeve cannot fill a 100-share lot.
CN_ETF_FALLBACK = "510300.SS"

# Industry / theme ETFs. Broad CSI 300 is the lot residual, not a scored sleeve.
CN_ETF_THEMES: dict[str, list[str]] = {
    "semis": [
        "512480.SS",  # Semiconductor
        "159813.SZ",
        "159995.SZ",  # Chip
    ],
    "ev": [
        "515030.SS",  # NEV (华夏新能源车; materials 159825 is 农业ETF)
        "515790.SS",  # PV / new energy
        "516160.SS",
    ],
    "healthcare": [
        "512010.SS",
        "159929.SZ",
        "158003.SZ",  # 港医嘉实 (materials)
    ],
    "defense": [
        "512710.SS",
        "512660.SS",
        "158009.SZ",  # 航天南方 (materials)
    ],
}

CN_ETF_THEME_NAMES: tuple[str, ...] = tuple(CN_ETF_THEMES.keys())

CN_ETF_NAMES: dict[str, str] = {
    "510300.SS": "CSI 300 ETF",
    "512480.SS": "Semiconductor ETF",
    "159813.SZ": "Semiconductor ETF (SZ)",
    "159995.SZ": "Chip ETF",
    "515030.SS": "NEV ETF",
    "515790.SS": "Photovoltaic ETF",
    "516160.SS": "New Energy ETF",
    "512010.SS": "Healthcare ETF",
    "159929.SZ": "Healthcare ETF (SZ)",
    "158003.SZ": "港医嘉实",
    "512710.SS": "Defense ETF",
    "512660.SS": "Defense ETF (Guojun)",
    "158009.SZ": "航天南方",
}

CN_STOCK_UNIVERSE: dict[str, str] = {
    "600519.SS": "Kweichow Moutai",
    "601318.SS": "Ping An Insurance",
    "600036.SS": "China Merchants Bank",
    "000333.SZ": "Midea Group",
    "600276.SS": "Jiangsu Hengrui Medicine",
    "600900.SS": "China Yangtze Power",
    "000001.SZ": "Ping An Bank",
    "000858.SZ": "Wuliangye",
    "300750.SZ": "CATL",
    "002594.SZ": "BYD",
    "688981.SS": "SMIC",
}

CN_UNIVERSE: dict[str, str] = {**CN_STOCK_UNIVERSE, **CN_ETF_NAMES}


def canonical_cn_symbol(raw: str) -> str:
    """Map a ticker to ``XXXXXX.SS`` / ``XXXXXX.SZ`` without constructing an adapter."""
    s = raw.strip().upper().replace(".SH", ".SS")
    if s.endswith(".SS") or s.endswith(".SZ"):
        code, _, exch = s.partition(".")
        return f"{code.zfill(6)}.{exch}"
    code = s.split(".")[0].zfill(6)
    if code.startswith(("5", "6", "9")):
        return f"{code}.SS"
    return f"{code}.SZ"


def all_cn_etf_symbols() -> list[str]:
    """Flatten the industry pool, preserving theme order and uniqueness."""
    seen: set[str] = set()
    out: list[str] = []
    for members in CN_ETF_THEMES.values():
        for symbol in members:
            if symbol not in seen:
                seen.add(symbol)
                out.append(symbol)
    return out


def cn_theme_of(symbol: str) -> str | None:
    """Return the industry sleeve for an ETF, if any."""
    canonical = canonical_cn_symbol(symbol)
    for name, members in CN_ETF_THEMES.items():
        if canonical in members:
            return name
    return None


class AkShareCNProvider(DataProvider):
    """Eastmoney A-share / ETF OHLCV via AkShare. Canonical symbols are ``XXXXXX.SS/SZ``."""

    _MINUTE = {"1m": "1", "5m": "5", "15m": "15", "30m": "30", "1h": "60"}
    _ETF_PREFIXES = ("15", "16", "50", "51", "52", "56", "58")

    def fetch(
        self,
        symbol: str,
        start: str | datetime,
        end: str | datetime,
        interval: str = "1d",
    ) -> pd.DataFrame:
        try:
            import akshare as ak
        except ImportError as exc:
            raise ValueError("A-share data requires akshare. Install with: pip install -e '.[paper]'") from exc

        code = symbol.split(".")[0]
        start_ts = pd.Timestamp(start)
        end_ts = pd.Timestamp(end)

        if interval == "1d":
            raw = self._daily_raw(ak, code, start_ts, end_ts)
            if raw is None or raw.empty:
                raise ValueError(f"No data returned for {symbol} ({start} to {end})")
            return self._daily_frame(raw)

        period = self._MINUTE.get(interval)
        if period is None:
            raise ValueError(f"Unsupported A-share interval: {interval}")
        raw = ak.stock_zh_a_hist_min_em(
            symbol=code,
            start_date=start_ts.strftime("%Y-%m-%d %H:%M:%S"),
            end_date=end_ts.strftime("%Y-%m-%d %H:%M:%S"),
            period=period,
            adjust="qfq",
        )
        if raw is None or raw.empty:
            raise ValueError(f"No data returned for {symbol} ({start} to {end})")
        return self._minute_frame(raw)

    def _daily_raw(self, ak, code: str, start_ts: pd.Timestamp, end_ts: pd.Timestamp) -> pd.DataFrame | None:
        start_s = start_ts.strftime("%Y%m%d")
        end_s = end_ts.strftime("%Y%m%d")
        if code.startswith(self._ETF_PREFIXES):
            try:
                raw = ak.fund_etf_hist_em(
                    symbol=code,
                    period="daily",
                    start_date=start_s,
                    end_date=end_s,
                    adjust="qfq",
                )
                if raw is not None and not raw.empty:
                    return raw
            except Exception:
                pass
        return ak.stock_zh_a_hist(
            symbol=code,
            period="daily",
            start_date=start_s,
            end_date=end_s,
            adjust="qfq",
        )

    @staticmethod
    def _rename_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
        mapping = {
            "日期": "date",
            "时间": "date",
            "开盘": "open",
            "最高": "high",
            "最低": "low",
            "收盘": "close",
            "收盘价": "close",
            "净值": "close",
            "成交量": "volume",
        }
        renamed = df.rename(columns={k: v for k, v in mapping.items() if k in df.columns})
        if "date" not in renamed.columns:
            renamed = renamed.copy()
            renamed.index.name = "date"
            renamed = renamed.reset_index()
        if "close" not in renamed.columns:
            raise ValueError("AkShare frame missing close/收盘 column")
        if "volume" not in renamed.columns:
            renamed = renamed.copy()
            renamed["volume"] = 0.0
        for col in ("open", "high", "low"):
            if col not in renamed.columns:
                renamed[col] = renamed["close"]
        out = renamed.set_index(pd.to_datetime(renamed["date"]))
        out.index.name = "date"
        out = out[["open", "high", "low", "close", "volume"]].astype(float)
        idx = pd.DatetimeIndex(pd.to_datetime(out.index))
        if idx.tz is not None:
            idx = idx.tz_convert(None)
        out.index = idx
        return out.sort_index()

    def _daily_frame(self, raw: pd.DataFrame) -> pd.DataFrame:
        return self._rename_ohlcv(raw)

    def _minute_frame(self, raw: pd.DataFrame) -> pd.DataFrame:
        return self._rename_ohlcv(raw)


class CNAdapter(MarketAdapter):
    market_id = "cn"
    profile = CN_PROFILE
    timezone = "Asia/Shanghai"
    session_hours = "09:30-11:30 / 13:00-15:00 CST"
    t_plus = 1

    def default_provider(self) -> DataProvider:
        from quantit.data.cn_csv import CompositeCNProvider

        return CompositeCNProvider()

    def normalize_symbol(self, raw: str) -> str:
        return canonical_cn_symbol(raw)

    def lot_size(self, symbol: str) -> int:
        return 100

    def universe(self) -> dict[str, str]:
        return CN_UNIVERSE
