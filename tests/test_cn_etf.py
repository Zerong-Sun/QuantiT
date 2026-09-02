"""A-share ETF rotation: CSV provider, policy scores, paper runner (no network)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest
import yaml

from quantit.data.cn_csv import CompositeCNProvider, CsvETFProvider, default_cn_etf_csv
from quantit.data.provider import DataProvider
from quantit.engine.backtester import Backtester
from quantit.features.cn_regime import compute_cn_etf_scores
from quantit.markets.assets import asset_class, is_allowed
from quantit.markets.cn import (
    CN_ETF_FALLBACK,
    CN_ETF_THEMES,
    CN_PROFILE,
    AkShareCNProvider,
    CNAdapter,
    all_cn_etf_symbols,
    canonical_cn_symbol,
    cn_theme_of,
)
from quantit.markets.hk import HKAdapter
from quantit.markets.registry import MarketRegistry
from quantit.markets.us import USAdapter
from quantit.paper.broker import PaperBroker
from quantit.paper.db import create_session
from quantit.paper.runner import PaperRunner
from quantit.policy.calendar import PolicyCalendar
from quantit.strategy.catalog import get_strategy, list_strategies
from quantit.strategy.regime import ThemeRotationStrategy, feasible_hk_weights
from quantit.strategy.signals import evaluate_signals

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "cn_etf_sample.csv"


def _ohlcv(n: int = 80, start: str = "2024-01-02", start_price: float = 1.0, volume: float = 1_000_000.0) -> pd.DataFrame:
    dates = pd.date_range(start, periods=n, freq="B")
    prices = [start_price + i * 0.01 for i in range(n)]
    return pd.DataFrame(
        {
            "open": prices,
            "high": [p + 0.02 for p in prices],
            "low": [p - 0.02 for p in prices],
            "close": prices,
            "volume": [volume] * n,
        },
        index=dates,
    )


class FakeProvider(DataProvider):
    def __init__(self, frames: dict[str, pd.DataFrame], fail: set[str] | None = None) -> None:
        self.frames = frames
        self.fail = fail or set()
        self.calls: list[tuple[str, str]] = []

    def fetch(self, symbol, start, end, interval: str = "1d") -> pd.DataFrame:
        self.calls.append((symbol, interval))
        if symbol in self.fail:
            raise ValueError(f"No data returned for {symbol}")
        if symbol not in self.frames:
            raise ValueError(f"No data returned for {symbol}")
        return self.frames[symbol].copy()


class TestUniverseAndClass:
    def test_theme_helpers(self) -> None:
        assert CN_ETF_FALLBACK == "510300.SS"
        assert set(CN_ETF_THEMES) == {"semis", "ev", "healthcare", "defense"}
        symbols = all_cn_etf_symbols()
        assert "512480.SS" in symbols
        assert "158003.SZ" in symbols
        assert "158009.SZ" in symbols
        assert CN_ETF_FALLBACK not in symbols
        assert cn_theme_of("515030.SS") == "ev"
        assert cn_theme_of("515030") == "ev"
        assert cn_theme_of("512480.sh") == "semis"
        assert cn_theme_of("510300.SS") is None
        assert canonical_cn_symbol("512480") == "512480.SS"
        assert canonical_cn_symbol("159813") == "159813.SZ"
        assert canonical_cn_symbol("510300.sh") == "510300.SS"

    def test_asset_class_prefixes(self) -> None:
        assert asset_class("cn", "510300.SS") == "etf"
        assert asset_class("cn", "159915.SZ") == "etf"
        assert asset_class("cn", "588000.SS") == "etf"
        assert asset_class("cn", "600519.SS") == "equity"
        assert is_allowed("cn", "510300.SS")
        assert "515030.SS" in all_cn_etf_symbols()
        assert "159825.SZ" not in all_cn_etf_symbols()


class TestCsvProvider:
    def test_vol_hand_to_volume_and_date_slice(self) -> None:
        provider = CsvETFProvider(path=FIXTURE)
        df = provider.fetch("510300.SS", "2024-06-04", "2024-06-05")
        assert list(df.columns) == ["open", "high", "low", "close", "volume"]
        assert len(df) == 2
        assert df.index.min() == pd.Timestamp("2024-06-04")
        # 11000 手 * 100
        assert df.loc["2024-06-04", "volume"] == pytest.approx(1_100_000.0)
        sz = provider.fetch("158003", "2024-06-03", "2024-06-05")
        assert len(sz) == 3
        assert sz["close"].iloc[-1] == pytest.approx(1.05)

    def test_numeric_code_column_keeps_leading_shape(self, tmp_path: Path) -> None:
        path = tmp_path / "codes.csv"
        path.write_text(
            "code,name,date,open,close,high,low,vol_hand,amt_yuan\n"
            "510300,沪深300ETF,2024-06-03,3.50,3.52,3.55,3.48,10000.0,3520000.0\n",
            encoding="utf-8",
        )
        df = CsvETFProvider(path=path).fetch("510300.SS", "2024-06-03", "2024-06-03")
        assert len(df) == 1
        assert df["close"].iloc[0] == pytest.approx(3.52)

    def test_missing_symbol_raises(self) -> None:
        provider = CsvETFProvider(path=FIXTURE)
        with pytest.raises(ValueError, match="No data"):
            provider.fetch("159915.SZ", "2024-06-03", "2024-06-05")

    def test_minute_interval_rejected(self) -> None:
        provider = CsvETFProvider(path=FIXTURE)
        with pytest.raises(ValueError, match="interval"):
            provider.fetch("510300.SS", "2024-06-03", "2024-06-05", interval="5m")


class TestCompositeProvider:
    def test_csv_covers_request_skips_live(self) -> None:
        live = FakeProvider({"510300.SS": _ohlcv(n=5, start="2024-01-02")})
        composite = CompositeCNProvider(csv=CsvETFProvider(path=FIXTURE), live=live)
        df = composite.fetch("510300.SS", "2024-06-03", "2024-06-05")
        assert live.calls == []
        assert len(df) == 3
        assert df["close"].iloc[-1] == pytest.approx(3.60)

    def test_csv_wins_on_overlap(self) -> None:
        live_df = _ohlcv(n=5, start="2024-06-03", start_price=9.0)
        live = FakeProvider({"512480.SS": live_df})
        composite = CompositeCNProvider(csv=CsvETFProvider(path=FIXTURE), live=live)
        df = composite.fetch("512480.SS", "2024-05-01", "2024-06-07")
        assert live.calls
        # overlapping 2024-06-03..05 should keep CSV closes (~0.91/0.93/0.95), not 9.x
        overlap = df.loc["2024-06-03":"2024-06-05"]
        assert overlap["close"].iloc[0] == pytest.approx(0.91)
        assert overlap["close"].iloc[-1] == pytest.approx(0.95)

    def test_minutes_go_to_live(self) -> None:
        live = FakeProvider({"510300.SS": _ohlcv(n=3, start="2024-06-03")})
        composite = CompositeCNProvider(csv=CsvETFProvider(path=FIXTURE), live=live)
        composite.fetch("510300.SS", "2024-06-03", "2024-06-05", interval="5m")
        assert live.calls == [("510300.SS", "5m")]

    def test_weekend_start_still_covered_by_csv(self) -> None:
        live = FakeProvider({"510300.SS": _ohlcv(n=5, start="2024-01-02")})
        composite = CompositeCNProvider(csv=CsvETFProvider(path=FIXTURE), live=live)
        df = composite.fetch("510300.SS", "2024-06-01", "2024-06-05")
        assert live.calls == []
        assert len(df) == 3

    def test_missing_csv_uses_live(self, tmp_path: Path) -> None:
        live = FakeProvider({"510300.SS": _ohlcv(n=3, start="2024-06-03", start_price=9.0)})
        composite = CompositeCNProvider(csv=CsvETFProvider(path=tmp_path / "absent.csv"), live=live)
        df = composite.fetch("510300.SS", "2024-06-03", "2024-06-05")
        assert live.calls == [("510300.SS", "1d")]
        assert df["close"].iloc[0] == pytest.approx(9.0)

    def test_bogus_env_csv_falls_back(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("QUANTIT_CN_ETF_CSV", str(tmp_path / "missing.csv"))
        result = default_cn_etf_csv()
        assert result != tmp_path / "missing.csv"
        if result is not None:
            assert result.is_file()


class TestAkShareRename:
    def test_nav_column_and_naive_index(self) -> None:
        raw = pd.DataFrame({"日期": ["2024-06-03"], "净值": [1.23], "成交量": [100.0]})
        out = AkShareCNProvider._rename_ohlcv(raw)
        assert list(out.columns) == ["open", "high", "low", "close", "volume"]
        assert out["close"].iloc[0] == pytest.approx(1.23)
        assert out["open"].iloc[0] == pytest.approx(1.23)
        assert out.index.tz is None
        assert out.index[0] == pd.Timestamp("2024-06-03")

    def test_aware_index_is_stripped(self) -> None:
        raw = pd.DataFrame(
            {
                "日期": pd.to_datetime(["2024-06-03 00:00:00+00:00"]),
                "开盘": [1.0],
                "最高": [1.1],
                "最低": [0.9],
                "收盘": [1.05],
                "成交量": [10.0],
            }
        )
        out = AkShareCNProvider._rename_ohlcv(raw)
        assert out.index.tz is None
        assert out["close"].iloc[0] == pytest.approx(1.05)


class TestPolicyCalendarCn:
    def test_load_cn_and_asof_gate(self) -> None:
        cal = PolicyCalendar.load_cn()
        assert set(cal.themes) == {"semis", "ev", "healthcare", "defense"}
        known = cal.scores_at("2024-10-15", asof="2026-09-02")
        assert known["semis"] != 0 or known["ev"] != 0 or known["defense"] != 0
        future = cal.scores_at("2026-12-15", asof="2026-09-02")
        assert future == {"semis": 0, "ev": 0, "healthcare": 0, "defense": 0}

    def test_packaged_yaml_parses(self) -> None:
        path = Path(__file__).resolve().parents[1] / "quantit" / "policy" / "data" / "cn_etf_regimes.yaml"
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert payload["themes"] == ["semis", "ev", "healthcare", "defense"]
        assert "regimes" in payload


class TestCnEtfScores:
    def test_four_theme_columns(self) -> None:
        n = 80
        ohlcv = {
            "512480.SS": _ohlcv(n, "2020-01-01", 1.0, volume=3_000_000),
            "515030.SS": _ohlcv(n, "2020-01-01", 1.2, volume=2_000_000),
            "512010.SS": _ohlcv(n, "2020-01-01", 1.1, volume=1_500_000),
            "512710.SS": _ohlcv(n, "2020-01-01", 0.9, volume=1_200_000),
            "510300.SS": _ohlcv(n, "2020-01-01", 3.5, volume=5_000_000),
        }
        macros = pd.DataFrame(
            {
                "dxy": [100 + i * 0.01 for i in range(n)],
                "us10y": [1.5 + i * 0.001 for i in range(n)],
                "nasdaq": [8000 + i * 2 for i in range(n)],
                "cny": [6.9 + i * 0.001 for i in range(n)],
            },
            index=ohlcv["510300.SS"].index,
        )
        yaml_text = """
themes: [semis, ev, healthcare, defense]
regimes:
  - name: ease
    start: 2020-01-01
    end: 2020-12-31
    scores: {semis: 1, ev: 0, healthcare: 0, defense: 0}
"""
        cal = PolicyCalendar.from_yaml(yaml_text)
        themes = {
            "semis": ["512480.SS"],
            "ev": ["515030.SS"],
            "healthcare": ["512010.SS"],
            "defense": ["512710.SS"],
        }
        scores = compute_cn_etf_scores(ohlcv, macros, calendar=cal, themes=themes)
        assert list(scores.columns) == ["semis", "ev", "healthcare", "defense"]
        assert len(scores) == n
        assert scores.notna().any().any()

    def test_month_end_strategy_trades(self) -> None:
        n = 80
        a = _ohlcv(n, "2020-01-01", 1.0)
        b = _ohlcv(n, "2020-01-01", 1.2)
        themes = {"semis": ["AAA.SS"], "ev": ["BBB.SZ"]}
        scores = pd.DataFrame({"semis": [1.0] * n, "ev": [-0.2] * n}, index=a.index)
        strategy = ThemeRotationStrategy(scores=scores, themes=themes, turnover_band=0.0)
        result = Backtester(
            initial_cash=1_000_000,
            commission_rate=CN_PROFILE.commission_rate,
            slippage_rate=0.0,
            fill_on="same_close",
        ).run(strategy, {"AAA.SS": a, "BBB.SZ": b}, symbol="CN-ETF")
        assert len(result.trades) > 0
        assert {t.symbol for t in result.trades} <= {"AAA.SS", "BBB.SZ"}

    def test_lot_residual_goes_to_csi300(self) -> None:
        names = ["512480.SS", "159813.SZ", "159995.SZ"]
        weight = 0.40 / len(names)
        target = {s: weight for s in names}
        prices = {s: 50.0 for s in names}
        prices[CN_ETF_FALLBACK] = 3.5
        lots = {s: 100 for s in names}
        lots[CN_ETF_FALLBACK] = 100
        out = feasible_hk_weights(
            target, prices, equity=2_000.0, lot_sizes=lots, fallback=CN_ETF_FALLBACK
        )
        assert all(name not in out for name in names)
        assert out[CN_ETF_FALLBACK] == pytest.approx(0.40)


class TestCatalogAndSignals:
    def test_catalog_lists_cn(self) -> None:
        entries = list_strategies("cn")
        assert [e["id"] for e in entries] == ["cn_etf_rotation"]
        entry = get_strategy("cn_etf_rotation")
        assert entry is not None
        assert "cn" in entry["markets"]
        assert "semis" in (entry.get("universe") or {})

    def test_evaluate_member_and_outsider(self) -> None:
        inside = evaluate_signals("cn", "512480.SS", _ohlcv())
        assert inside["signals"][0]["strategy_id"] == "cn_etf_rotation"
        assert inside["signals"][0]["action"] == "watch"
        outside = evaluate_signals("cn", "600519.SS", _ohlcv())
        assert outside["signals"][0]["action"] == "hold"

    def test_signal_accepts_unnormalized_ticker(self) -> None:
        inside = evaluate_signals("cn", "512480.sh", _ohlcv())
        sig = inside["signals"][0]
        assert sig["action"] == "watch"
        assert sig["values"]["theme"] == "semis"
        assert "Semiconductor" in sig["values"]["name"]


class TestPaperCostsAndRunner:
    def _broker(self, frames: dict[str, pd.DataFrame], when: datetime) -> PaperBroker:
        registry = MarketRegistry()
        registry.register(USAdapter(provider=FakeProvider({"AAPL": _ohlcv()})))
        registry.register(HKAdapter(provider=FakeProvider({"0700.HK": _ohlcv()})))
        registry.register(CNAdapter(provider=FakeProvider(frames)))
        session = create_session("sqlite:///:memory:")
        return PaperBroker(session, registry=registry, now=lambda: when)

    def test_etf_buy_has_no_stamp_duty(self) -> None:
        frames = {"510300.SS": _ohlcv(n=5, start="2024-06-03", start_price=3.5)}
        broker = self._broker(frames, datetime(2024, 6, 10, 10, 0, 0))
        broker.ensure_accounts()
        before = broker.get_account("cn").cash
        order = broker.place_order("cn", "510300.SS", "buy", 100)
        assert order.status == "filled"
        last = 3.5 + 4 * 0.01
        fill = last * (1 + CN_PROFILE.slippage_rate)
        expected_comm = fill * 100 * CN_PROFILE.commission_rate
        assert order.commission == pytest.approx(expected_comm)
        spent = before - broker.get_account("cn").cash
        assert spent == pytest.approx(fill * 100 + expected_comm)

    def test_equity_sell_charges_stamp(self) -> None:
        frames = {"600519.SS": _ohlcv(n=5, start="2024-06-03", start_price=10.0)}
        broker = self._broker(frames, datetime(2024, 6, 10, 10, 0, 0))
        broker.ensure_accounts()
        buy = broker.place_order("cn", "600519.SS", "buy", 100)
        assert buy.status == "filled"
        broker._now = lambda: datetime(2024, 6, 11, 10, 0, 0)
        sell = broker.place_order("cn", "600519.SS", "sell", 100)
        assert sell.status == "filled"
        last = 10.0 + 4 * 0.01
        fill = last * (1 - CN_PROFILE.slippage_rate)
        expected = fill * 100 * (CN_PROFILE.commission_rate + CN_PROFILE.stamp_duty_rate)
        assert sell.commission == pytest.approx(expected)

    def test_etf_sell_next_day_has_no_stamp(self) -> None:
        frames = {"510300.SS": _ohlcv(n=5, start="2024-06-03", start_price=3.5)}
        broker = self._broker(frames, datetime(2024, 6, 10, 10, 0, 0))
        broker.ensure_accounts()
        buy = broker.place_order("cn", "510300.SS", "buy", 100)
        assert buy.status == "filled"
        broker._now = lambda: datetime(2024, 6, 11, 10, 0, 0)
        sell = broker.place_order("cn", "510300.SS", "sell", 100)
        assert sell.status == "filled"
        last = 3.5 + 4 * 0.01
        fill = last * (1 - CN_PROFILE.slippage_rate)
        expected = fill * 100 * CN_PROFILE.commission_rate
        assert sell.commission == pytest.approx(expected)

    def test_t_plus_still_blocks_etf_same_day_sell(self) -> None:
        frames = {"510300.SS": _ohlcv(n=5, start="2024-06-03", start_price=3.5)}
        broker = self._broker(frames, datetime(2024, 6, 10, 10, 0, 0))
        broker.ensure_accounts()
        buy = broker.place_order("cn", "510300", "buy", 100)
        assert buy.status == "filled"
        sell = broker.place_order("cn", "510300", "sell", 100)
        assert sell.status == "rejected"
        assert "t+1" in (sell.reject_reason or "").lower()

    def test_runner_skips_non_month_end(self) -> None:
        frames = {
            "510300.SS": _ohlcv(n=45, start="2024-05-01", start_price=3.5),
            "512480.SS": _ohlcv(n=45, start="2024-05-01", start_price=1.0),
        }
        broker = self._broker(frames, datetime(2024, 5, 15, 10, 0, 0))
        broker.ensure_accounts()
        idx = frames["510300.SS"].index
        scores = pd.DataFrame(
            {"semis": [2.0] * len(idx), "ev": [-1.0] * len(idx), "healthcare": [-1.0] * len(idx), "defense": [-1.0] * len(idx)},
            index=idx,
        )
        runner = PaperRunner(broker, us_watch=(), hk_warrants=(), hk_scores=None, cn_scores=scores)
        actions = runner.tick()
        cn_fills = [a for a in actions if a["market_id"] == "cn" and a["status"] == "filled"]
        assert cn_fills == []

    def test_runner_rebalances_on_month_end_in_lots_of_100(self) -> None:
        frames = {
            "510300.SS": _ohlcv(n=45, start="2024-05-01", start_price=3.5),
            "512480.SS": _ohlcv(n=45, start="2024-05-01", start_price=1.0),
        }
        # 2024-05-31 is Friday, last session of May.
        broker = self._broker(frames, datetime(2024, 5, 31, 15, 0, 0))
        broker.ensure_accounts()
        idx = frames["510300.SS"].index
        scores = pd.DataFrame(
            {"semis": [2.0] * len(idx), "ev": [-1.0] * len(idx), "healthcare": [-1.0] * len(idx), "defense": [-1.0] * len(idx)},
            index=idx,
        )
        runner = PaperRunner(broker, us_watch=(), hk_warrants=(), hk_scores=None, cn_scores=scores)
        actions = runner.tick()
        cn_fills = [a for a in actions if a["market_id"] == "cn" and a["status"] == "filled"]
        assert cn_fills
        for row in cn_fills:
            assert row["quantity"] % 100 == 0
        snap = runner.snapshot()
        assert "cn" in snap["watchlists"]
        assert "512480.SS" in snap["watchlists"]["cn"]
