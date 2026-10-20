from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from closeloop.model.evaluation import daily_ic, forward_labels, gate_reasons, lag_features, training_dates
from closeloop.model.portfolio import PortfolioConfig, performance, simulate


def data(values):
    close = pd.DataFrame(values, index=pd.bdate_range("2024-01-01", periods=len(next(iter(values.values())))))
    return close, pd.DataFrame(1000.0, index=close.index, columns=close.columns)


def test_lag_uses_calendar_not_next_observed_stock_row():
    dates = pd.bdate_range("2024-01-01", periods=4)
    index = pd.MultiIndex.from_tuples([(dates[0], "A"), (dates[2], "A"), (dates[3], "A")],
                                    names=["date", "instrument"])
    lagged = lag_features(pd.DataFrame({"x": [10, 30, 40]}, index=index), dates)
    assert lagged.loc[(dates[1], "A"), "x"] == 10
    assert pd.isna(lagged.loc[(dates[2], "A"), "x"])
    assert lagged.loc[(dates[3], "A"), "x"] == 30
    assert pd.isna(lagged.loc[(dates[0], "A"), "x"])


@pytest.mark.parametrize("horizon", [1, 5, 10])
def test_training_labels_end_before_boundary_with_embargo(horizon):
    dates = pd.bdate_range("2024-01-01", periods=80)
    train = training_dates(dates, dates[50], horizon, 5)
    last = dates.get_loc(train[-1])
    assert last + horizon < 50 - 5
    assert not train.intersection(dates[50:]).size


def test_missing_forward_price_not_filled():
    close, _ = data({"A": [100, np.nan, 120]})
    labels = forward_labels(close, 1)
    assert labels.isna().all()


def test_costs_cash_and_initial_drawdown_are_accounted_for():
    close, volume = data({"A": [100.0] * 5})
    scores = close * 0 + 1
    cfg = PortfolioConfig(top_k=1, rebalance=10, turnover_limit=2, buy_cost=.01, sell_cost=.01)
    curve = simulate(scores, close, volume, cfg, start=close.index[1], end=close.index[-1])
    assert len(curve) == 3  # no return after last close
    assert curve.net_return.iloc[0] == pytest.approx(-.01 / 1.01)
    assert curve.net_return.iloc[1:].eq(0).all()
    assert curve.cash_weight.ge(-1e-12).all()
    assert performance(curve)["max_drawdown"] == pytest.approx(-.01 / 1.01)
    free = simulate(scores, close, volume, replace(cfg, buy_cost=0, sell_cost=0),
                    start=close.index[1], end=close.index[-1])
    assert free.net_return.eq(0).all()


def test_turnover_cap_and_signal_reversal_cost():
    close, volume = data({"A": [100.0] * 6, "B": [100.0] * 6})
    scores = pd.DataFrame({"A": [2, 2, 0, 0, 0, 0], "B": [0, 0, 2, 2, 2, 2]}, index=close.index)
    curve = simulate(scores, close, volume, PortfolioConfig(top_k=1, rebalance=1, turnover_limit=.4),
                     start=close.index[1], end=close.index[-1])
    assert (curve.turnover <= .4 + 1e-12).all()
    assert curve.cost.iloc[1] > 0
    assert curve.net_return.sum() < 0
    assert curve.cash_weight.ge(0).all()


def test_zero_volume_blocks_fill_and_missing_held_mark_is_flagged():
    close, volume = data({"A": [100.0, 100.0, np.nan, 100.0, 100.0]})
    scores = close * 0 + 1
    config = PortfolioConfig(top_k=1, turnover_limit=2)
    curve = simulate(scores, close, volume, config, start=close.index[1], end=close.index[-1])
    assert curve.stale_valuation.any()
    volume.iloc[1] = 0
    blocked = simulate(scores, close, volume, config, start=close.index[1], end=close.index[1])
    assert blocked.turnover.iloc[0] == 0


def test_limit_day_does_not_fill():
    close, volume = data({"A": [100.0, 110.0, 111.0]})
    curve = simulate(close, close, volume, PortfolioConfig(top_k=1),
                     start=close.index[1], end=close.index[1])
    assert curve.turnover.iloc[0] == 0


def test_future_scores_do_not_change_earlier_equity():
    close, volume = data({"A": [100, 101, 102, 103, 104, 105], "B": [100, 99, 98, 97, 96, 95]})
    scores = pd.DataFrame({"A": [2] * 6, "B": [1] * 6}, index=close.index)
    cfg = PortfolioConfig(top_k=1, rebalance=1)
    original = simulate(scores, close, volume, cfg, start=close.index[1], end=close.index[-1])
    scores.loc[close.index[3]:, "B"] = 100
    changed = simulate(scores, close, volume, cfg, start=close.index[1], end=close.index[-1])
    pd.testing.assert_frame_equal(original.iloc[:2], changed.iloc[:2])


def test_rank_ic_is_daily_not_pooled():
    index = pd.MultiIndex.from_product([pd.bdate_range("2024-01-01", periods=2), list("ABCDE")],
                                      names=["date", "instrument"])
    pred = pd.Series([1, 2, 3, 4, 5, 101, 102, 103, 104, 105], index=index)
    label = pd.Series([5, 4, 3, 2, 1, 105, 104, 103, 102, 101], index=index)
    assert pred.corr(label) > .9
    assert daily_ic(pred, label)["rank_ic"] == pytest.approx(-1)


def test_gates_fail_on_missing_metrics_and_stale_valuations():
    empty = performance(pd.DataFrame())
    assert gate_reasons(empty, empty, [], {"rank_ic": None})
    good = {"sessions": 200, "net_return": .1, "max_drawdown": -.05, "sharpe": 1,
            "stale_valuation_sessions": 1}
    reasons = gate_reasons(good, {"net_return": .05}, [{"net_return": .02}] * 3, {"rank_ic": .03})
    assert reasons == ["持仓估值存在缺失行情"]


@pytest.mark.parametrize("kwargs", [{"top_k": 0}, {"rebalance": 0}, {"turnover_limit": 0},
                                   {"buy_cost": -1}, {"sell_cost": 1}, {"limit_threshold": 0}])
def test_invalid_portfolio_config_fails(kwargs):
    with pytest.raises(ValueError):
        PortfolioConfig(**kwargs)


def test_model_fit_never_reads_future_rows_or_labels(monkeypatch):
    import sys
    from types import SimpleNamespace
    from closeloop.model.experiment import fit_model

    captured = []

    class CaptureModel:
        def __init__(self, **kwargs):
            pass

        def fit(self, x, y):
            captured.append((x.copy(), y.copy()))

    monkeypatch.setitem(sys.modules, "lightgbm", SimpleNamespace(LGBMRegressor=CaptureModel))
    dates = pd.bdate_range("2024-01-01", periods=100)
    index = pd.MultiIndex.from_product([dates, list("ABCDE")], names=["date", "instrument"])
    features = pd.DataFrame({"x": np.arange(len(index), dtype=float)}, index=index)
    labels = pd.Series(np.tile([1, 2, 3, 4, 5], len(dates)), index=index)
    allowed = training_dates(dates, dates[80], 5, 5)
    fit_model(features, labels, allowed, {}, 1)
    future = features.index.get_level_values("date") >= dates[70]
    features.loc[future] = 99999
    labels.loc[future] = -99999
    fit_model(features, labels, allowed, {}, 1)
    pd.testing.assert_frame_equal(captured[0][0], captured[1][0])
    pd.testing.assert_series_equal(captured[0][1], captured[1][1])
    assert captured[0][0].index.get_level_values("date").max() == dates[69]


def test_validation_selection_ignores_future_scores():
    from closeloop.model.experiment import select_portfolio

    close, volume = data({"A": np.linspace(100, 105, 25), "B": np.linspace(100, 95, 25)})
    scores = close * 0
    scores["A"] = 1
    args = (close, volume, close.index[1], close.index[10])
    config, trials = select_portfolio(scores, *args)
    scores.loc[close.index[12]:, "B"] = 9999
    after_config, after_trials = select_portfolio(scores, *args)
    assert after_config == config
    assert after_trials == trials
