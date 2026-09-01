"""Onshore A-share market profile and AkShare-backed adapter."""

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
    lot_size_note="A-shares trade in lots of 100; T+1 settlement.",
)

CN_UNIVERSE: dict[str, str] = {
    "600519.SS": "Kweichow Moutai",
    "601318.SS": "Ping An Insurance",
    "600036.SS": "China Merchants Bank",
    "000001.SZ": "Ping An Bank",
    "000858.SZ": "Wuliangye",
    "300750.SZ": "CATL",
    "002594.SZ": "BYD",
    "688981.SS": "SMIC",
}


class AkShareCNProvider(DataProvider):
    """Eastmoney A-share OHLCV via AkShare. Canonical symbols are ``XXXXXX.SS/SZ``."""

    _MINUTE = {"1m": "1", "5m": "5", "15m": "15", "30m": "30", "1h": "60"}

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
            raw = ak.stock_zh_a_hist(
                symbol=code,
                period="daily",
                start_date=start_ts.strftime("%Y%m%d"),
                end_date=end_ts.strftime("%Y%m%d"),
                adjust="qfq",
            )
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

    @staticmethod
    def _rename_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
        mapping = {
            "日期": "date",
            "时间": "date",
            "开盘": "open",
            "最高": "high",
            "最低": "low",
            "收盘": "close",
            "成交量": "volume",
        }
        renamed = df.rename(columns={k: v for k, v in mapping.items() if k in df.columns})
        if "date" not in renamed.columns:
            renamed = renamed.copy()
            renamed.index.name = "date"
            renamed = renamed.reset_index()
        out = renamed.set_index(pd.to_datetime(renamed["date"]))
        out.index.name = "date"
        out = out[["open", "high", "low", "close", "volume"]].astype(float)
        out.index = pd.to_datetime(out.index).tz_localize(None)
        return out.sort_index()

    def _daily_frame(self, raw: pd.DataFrame) -> pd.DataFrame:
        return self._rename_ohlcv(raw)

    def _minute_frame(self, raw: pd.DataFrame) -> pd.DataFrame:
        return self._rename_ohlcv(raw)


class CNAdapter(MarketAdapter):
    market_id = "cn"
    profile = CN_PROFILE
    timezone = "Asia/Shanghai"
    session_hours = "09:30-15:00 CST"
    t_plus = 1

    def default_provider(self) -> DataProvider:
        return AkShareCNProvider()

    def normalize_symbol(self, raw: str) -> str:
        s = raw.strip().upper().replace(".SH", ".SS")
        if s.endswith(".SS") or s.endswith(".SZ"):
            code, _, exch = s.partition(".")
            return f"{code.zfill(6)}.{exch}"
        code = s.split(".")[0].zfill(6)
        if code.startswith(("6", "9")):
            return f"{code}.SS"
        return f"{code}.SZ"

    def lot_size(self, symbol: str) -> int:
        return 100

    def universe(self) -> dict[str, str]:
        return CN_UNIVERSE
