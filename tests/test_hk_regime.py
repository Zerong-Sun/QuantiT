"""Tests for HK long-horizon theme rotation (no network)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
import yaml

from quantit.engine.backtester import Backtester
from quantit.features.regime import compute_theme_scores, scores_to_theme_weights
from quantit.markets.hk import HK_PROFILE, HSTECH_THEMES, all_hstech_symbols, theme_of
from quantit.policy.calendar import PolicyCalendar
from quantit.strategy.regime import ThemeRotationStrategy, is_month_end
from quantit.strategy.technical import MACrossoverStrategy


def _ohlcv(n: int, start: str, start_price: float, volume: float = 1_000_000.0) -> pd.DataFrame:
    dates = pd.date_range(start, periods=n, freq="B")
    prices = [start_price + i * 0.2 for i in range(n)]
    return pd.DataFrame(
        {
            "open": prices,
            "high": [p + 0.5 for p in prices],
            "low": [p - 0.5 for p in prices],
            "close": prices,
            "volume": [volume] * n,
        },
        index=dates,
    )


class TestMarketProfile:
    def test_stamp_duty_in_all_in_rate(self) -> None:
        assert HK_PROFILE.currency == "HKD"
        assert HK_PROFILE.stamp_duty_rate == 0.001
        assert HK_PROFILE.all_in_commission_rate == pytest.approx(
            HK_PROFILE.commission_rate + HK_PROFILE.stamp_duty_rate
        )

    def test_universe(self) -> None:
        symbols = all_hstech_symbols()
        assert "0700.HK" in symbols
        assert "9988.HK" in symbols
        assert theme_of("0700.HK") == "platforms"
        assert theme_of("0981.HK") == "semis"
        assert set(HSTECH_THEMES) == {"platforms", "hardware", "semis", "ev"}


class TestPolicyCalendar:
    def test_overlapping_regimes_clip(self) -> None:
        cal = PolicyCalendar.from_yaml(
            """
themes: [platforms, hardware, semis, ev]
regimes:
  - name: a
    start: 2021-01-01
    end: 2021-12-31
    scores: {platforms: -2, hardware: 0, semis: 0, ev: 0}
  - name: b
    start: 2021-06-01
    end: 2021-08-31
    scores: {platforms: -2, hardware: 0, semis: 0, ev: 0}
"""
        )
        mid = cal.scores_at("2021-07-15")
        assert mid["platforms"] == -2
        before = cal.scores_at("2021-02-01")
        assert before["platforms"] == -2
        outside = cal.scores_at("2020-01-01")
        assert outside["platforms"] == 0

    def test_default_yaml_loads(self) -> None:
        cal = PolicyCalendar.load_default()
        crack = cal.scores_at("2021-08-15")
        assert crack["platforms"] <= -1
        easing = cal.scores_at("2024-01-15")
        assert easing["platforms"] >= 0

    def test_packaged_yaml_parses(self) -> None:
        path = Path(__file__).resolve().parents[1] / "quantit" / "policy" / "data" / "hstech_regimes.yaml"
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert "regimes" in payload


class TestRegimeWeights:
    def test_cash_buffer_when_all_negative(self) -> None:
        weights = scores_to_theme_weights(
            {"platforms": -1.0, "hardware": -0.8, "semis": -1.2, "ev": -0.9},
            cash_threshold=-0.5,
            risk_off_invested=0.40,
        )
        assert pytest.approx(sum(weights.values()), abs=1e-9) == 0.40

    def test_equal_weight_when_scores_close(self) -> None:
        weights = scores_to_theme_weights(
            {"platforms": 0.1, "hardware": 0.12},
            cash_threshold=-0.5,
            equal_weight_band=0.25,
        )
        assert pytest.approx(weights["platforms"], abs=1e-9) == 0.5
        assert pytest.approx(sum(weights.values()), abs=1e-9) == 1.0


class TestMonthEnd:
    def test_last_business_day(self) -> None:
        dates = pd.date_range("2020-01-01", periods=45, freq="B")
        jan_end = [d for d in dates if d.month == 1][-1]
        jan_mid = [d for d in dates if d.month == 1][5]
        assert is_month_end(dates, jan_end)
        assert not is_month_end(dates, jan_mid)


class TestMultiAssetBacktest:
    def test_equity_curve_and_month_end_trades(self) -> None:
        n = 80
        a = _ohlcv(n, "2020-01-01", 50.0, volume=2_000_000)
        b = _ohlcv(n, "2020-01-01", 80.0, volume=1_500_000)
        themes = {"platforms": ["AAA.HK"], "hardware": ["BBB.HK"]}
        data = {"AAA.HK": a, "BBB.HK": b}
        idx = a.index
        scores = pd.DataFrame(
            {"platforms": [1.0] * n, "hardware": [-0.2] * n},
            index=idx,
        )
        strategy = ThemeRotationStrategy(scores=scores, themes=themes, turnover_band=0.0)
        result = Backtester(
            initial_cash=100_000,
            commission_rate=0.0,
            slippage_rate=0.0,
            fill_on="same_close",
        ).run(strategy, data, symbol="TEST-HK")
        assert not result.equity_curve.empty
        assert result.equity_curve.iloc[0] == 100_000
        assert len(result.trades) > 0
        assert {t.symbol for t in result.trades} <= {"AAA.HK", "BBB.HK"}

    def test_risk_off_raises_cash(self) -> None:
        n = 50
        a = _ohlcv(n, "2020-01-01", 10.0)
        b = _ohlcv(n, "2020-01-01", 10.0)
        themes = {"platforms": ["AAA.HK"], "hardware": ["BBB.HK"]}
        scores = pd.DataFrame(
            {"platforms": [-1.5] * n, "hardware": [-1.5] * n},
            index=a.index,
        )
        strategy = ThemeRotationStrategy(
            scores=scores,
            themes=themes,
            cash_threshold=-0.5,
            risk_off_invested=0.40,
            turnover_band=0.0,
        )
        result = Backtester(
            initial_cash=100_000,
            commission_rate=0.0,
            slippage_rate=0.0,
            fill_on="same_close",
        ).run(strategy, {"AAA.HK": a, "BBB.HK": b}, symbol="CASH")
        last = result.portfolio.history[-1]
        invested = last.equity - last.cash
        assert invested / last.equity < 0.55

    def test_single_symbol_api_unchanged(self) -> None:
        data = _ohlcv(60, "2020-01-01", 100.0)
        result = Backtester(initial_cash=50_000).run(
            MACrossoverStrategy(fast_period=5, slow_period=15),
            data,
            symbol="TEST",
        )
        assert result.symbol == "TEST"
        assert not result.equity_curve.empty


class TestComputeThemeScores:
    def test_offline_panel(self) -> None:
        n = 80
        ohlcv = {
            "0700.HK": _ohlcv(n, "2020-01-01", 300.0, volume=3_000_000),
            "1810.HK": _ohlcv(n, "2020-01-01", 20.0, volume=8_000_000),
        }
        macros = pd.DataFrame(
            {
                "dxy": [100 + i * 0.01 for i in range(n)],
                "us10y": [1.5 + i * 0.001 for i in range(n)],
                "nasdaq": [8000 + i * 2 for i in range(n)],
                "cny": [6.9 + i * 0.001 for i in range(n)],
                "hkd": [7.80] * n,
            },
            index=ohlcv["0700.HK"].index,
        )
        yaml_text = """
themes: [platforms, hardware]
regimes:
  - name: ease
    start: 2020-01-01
    end: 2020-12-31
    scores: {platforms: 1, hardware: 0}
"""
        cal = PolicyCalendar.from_yaml(yaml_text)
        themes = {"platforms": ["0700.HK"], "hardware": ["1810.HK"]}
        scores = compute_theme_scores(ohlcv, macros, calendar=cal, themes=themes)
        assert list(scores.columns) == ["platforms", "hardware"]
        assert len(scores) == n
        assert scores.notna().any().any()
