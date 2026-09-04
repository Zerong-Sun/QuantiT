"""WorldQuant 101 Formulaic Alphas on a Qlib-style OHLCV panel.

Formulas that call ``IndNeutralize`` or need ``cap`` are registered but raise
``UnsupportedAlphaError`` so they cannot silently leak a wrong number.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pandas as pd

from closeloop.data.protocol import add_returns, field_frame
from closeloop.factors import ops as O
from closeloop.factors.ops import UnsupportedOperatorError
from closeloop.factors.spec import FactorSpec

AlphaFn = Callable[["Fields"], pd.DataFrame]

INDUSTRY_OR_CAP: frozenset[str] = frozenset(
    {
        "048",
        "056",
        "058",
        "059",
        "063",
        "067",
        "069",
        "070",
        "076",
        "079",
        "080",
        "082",
        "087",
        "089",
        "090",
        "091",
        "093",
        "097",
        "100",
    }
)


class UnsupportedAlphaError(RuntimeError):
    def __init__(self, alpha_id: str, reason: str) -> None:
        self.alpha_id = alpha_id
        self.reason = reason
        super().__init__(f"alpha {alpha_id} unsupported: {reason}")


@dataclass
class Fields:
    open: pd.DataFrame
    high: pd.DataFrame
    low: pd.DataFrame
    close: pd.DataFrame
    volume: pd.DataFrame
    vwap: pd.DataFrame
    returns: pd.DataFrame
    industry: pd.DataFrame | None = None
    cap: pd.DataFrame | None = None

    @classmethod
    def from_panel(cls, panel: pd.DataFrame) -> Fields:
        if "returns" not in panel.columns.get_level_values("field"):
            panel = add_returns(panel)
        names = set(panel.columns.get_level_values("field"))
        return cls(
            open=field_frame(panel, "open"),
            high=field_frame(panel, "high"),
            low=field_frame(panel, "low"),
            close=field_frame(panel, "close"),
            volume=field_frame(panel, "volume"),
            vwap=field_frame(panel, "vwap"),
            returns=field_frame(panel, "returns"),
            industry=field_frame(panel, "industry") if "industry" in names else None,
            cap=field_frame(panel, "cap") if "cap" in names else None,
        )


def _adv(f: Fields, d: int) -> pd.DataFrame:
    return O.adv(f.volume, d)


def _a001(f: Fields) -> pd.DataFrame:
    """rank(Ts_ArgMax(SignedPower(((returns<0)?stddev(returns,20):close), 2), 5)) - 0.5"""
    inner = O.ternary(f.returns < 0, O.stddev(f.returns, 20), f.close)
    return O.rank(O.ts_argmax(O.signedpower(inner, 2.0), 5)) - 0.5


def _a002(f: Fields) -> pd.DataFrame:
    """(-1 * correlation(rank(delta(log(volume), 2)), rank(((close-open)/open)), 6))"""
    return -O.correlation(
        O.rank(O.delta(O.log(f.volume), 2)),
        O.rank((f.close - f.open) / f.open),
        6,
    )


def _a003(f: Fields) -> pd.DataFrame:
    return -O.correlation(O.rank(f.open), O.rank(f.volume), 10)


def _a004(f: Fields) -> pd.DataFrame:
    return -O.ts_rank(O.rank(f.low), 9)


def _a005(f: Fields) -> pd.DataFrame:
    return O.rank(f.open - O.ts_mean(f.vwap, 10)) * (-O.abs_(O.rank(f.close - f.vwap)))


def _a006(f: Fields) -> pd.DataFrame:
    return -O.correlation(f.open, f.volume, 10)


def _a007(f: Fields) -> pd.DataFrame:
    cond = _adv(f, 20) < f.volume
    left = -O.ts_rank(O.abs_(O.delta(f.close, 7)), 60) * O.sign(O.delta(f.close, 7))
    return O.ternary(cond, left, -1.0)


def _a008(f: Fields) -> pd.DataFrame:
    s = O.ts_sum(f.open, 5) * O.ts_sum(f.returns, 5)
    return -O.rank(s - O.delay(s, 10))


def _a009(f: Fields) -> pd.DataFrame:
    d1 = O.delta(f.close, 1)
    return O.ternary(
        O.ts_min(d1, 5) > 0,
        d1,
        O.ternary(O.ts_max(d1, 5) < 0, d1, -d1),
    )


def _a010(f: Fields) -> pd.DataFrame:
    d1 = O.delta(f.close, 1)
    inner = O.ternary(O.ts_min(d1, 4) > 0, d1, O.ternary(O.ts_max(d1, 4) < 0, d1, -d1))
    return O.rank(inner)


def _a011(f: Fields) -> pd.DataFrame:
    gap = f.vwap - f.close
    return (O.rank(O.ts_max(gap, 3)) + O.rank(O.ts_min(gap, 3))) * O.rank(O.delta(f.volume, 3))


def _a012(f: Fields) -> pd.DataFrame:
    return O.sign(O.delta(f.volume, 1)) * (-O.delta(f.close, 1))


def _a013(f: Fields) -> pd.DataFrame:
    return -O.rank(O.covariance(O.rank(f.close), O.rank(f.volume), 5))


def _a014(f: Fields) -> pd.DataFrame:
    return (-O.rank(O.delta(f.returns, 3))) * O.correlation(f.open, f.volume, 10)


def _a015(f: Fields) -> pd.DataFrame:
    return -O.ts_sum(O.rank(O.correlation(O.rank(f.high), O.rank(f.volume), 3)), 3)


def _a016(f: Fields) -> pd.DataFrame:
    return -O.rank(O.covariance(O.rank(f.high), O.rank(f.volume), 5))


def _a017(f: Fields) -> pd.DataFrame:
    return (
        (-O.rank(O.ts_rank(f.close, 10)))
        * O.rank(O.delta(O.delta(f.close, 1), 1))
        * O.rank(O.ts_rank(f.volume / _adv(f, 20), 5))
    )


def _a018(f: Fields) -> pd.DataFrame:
    return -O.rank(O.stddev(O.abs_(f.close - f.open), 5) + (f.close - f.open) + O.correlation(f.close, f.open, 10))


def _a019(f: Fields) -> pd.DataFrame:
    return (-O.sign((f.close - O.delay(f.close, 7)) + O.delta(f.close, 7))) * (
        1 + O.rank(1 + O.ts_sum(f.returns, 250))
    )


def _a020(f: Fields) -> pd.DataFrame:
    return (
        (-O.rank(f.open - O.delay(f.high, 1)))
        * O.rank(f.open - O.delay(f.close, 1))
        * O.rank(f.open - O.delay(f.low, 1))
    )


def _a021(f: Fields) -> pd.DataFrame:
    cond1 = O.ts_mean(f.close, 8) + O.stddev(f.close, 8) < O.ts_mean(f.close, 2)
    cond2 = O.ts_mean(f.close, 2) < O.ts_mean(f.close, 8) - O.stddev(f.close, 8)
    cond3 = f.volume / _adv(f, 20) >= 1
    return O.ternary(cond1, -1.0, O.ternary(cond2, 1.0, O.ternary(cond3, 1.0, -1.0)))


def _a022(f: Fields) -> pd.DataFrame:
    return -(O.delta(O.correlation(f.high, f.volume, 5), 5) * O.rank(O.stddev(f.close, 20)))


def _a023(f: Fields) -> pd.DataFrame:
    return O.ternary(O.ts_mean(f.high, 20) < f.high, -O.delta(f.high, 2), 0.0)


def _a024(f: Fields) -> pd.DataFrame:
    ratio = O.delta(O.ts_mean(f.close, 100), 100) / O.delay(f.close, 100)
    return O.ternary(ratio <= 0.05, -(f.close - O.ts_min(f.close, 100)), -O.delta(f.close, 3))


def _a025(f: Fields) -> pd.DataFrame:
    return O.rank(((-f.returns) * _adv(f, 20) * f.vwap) * (f.high - f.close))


def _a026(f: Fields) -> pd.DataFrame:
    return -O.ts_max(O.correlation(O.ts_rank(f.volume, 5), O.ts_rank(f.high, 5), 5), 3)


def _a027(f: Fields) -> pd.DataFrame:
    inner = O.rank(O.ts_mean(O.correlation(O.rank(f.volume), O.rank(f.vwap), 6), 2))
    return O.ternary(inner > 0.5, -1.0, 1.0)


def _a028(f: Fields) -> pd.DataFrame:
    return O.scale(O.correlation(_adv(f, 20), f.low, 5) + (f.high + f.low) / 2 - f.close)


def _a029(f: Fields) -> pd.DataFrame:
    inner = O.rank(O.rank((-O.rank(O.delta(f.close - 1, 5)))))
    a = O.ts_min(inner, 2)
    b = O.log(O.ts_sum(O.rank(O.rank(O.scale(a))), 1))
    return O.minimum(O.ts_product(O.rank(O.rank(b)), 5), O.ts_rank(O.delay(-f.returns, 6), 5)) + O.ts_rank(
        O.delay(-f.returns, 6), 5
    )


def _a030(f: Fields) -> pd.DataFrame:
    signs = (
        O.sign(f.close - O.delay(f.close, 1))
        + O.sign(O.delay(f.close, 1) - O.delay(f.close, 2))
        + O.sign(O.delay(f.close, 2) - O.delay(f.close, 3))
    )
    return ((1.0 - O.rank(signs)) * O.ts_sum(f.volume, 5)) / O.ts_sum(f.volume, 20)


def _a031(f: Fields) -> pd.DataFrame:
    return (
        O.rank(O.rank(O.rank(O.decay_linear(-O.rank(O.rank(O.delta(f.close, 10))), 10))))
        + O.rank(-O.delta(f.close, 3))
        + O.sign(O.scale(O.correlation(_adv(f, 20), f.low, 12)))
    )


def _a032(f: Fields) -> pd.DataFrame:
    return O.scale(O.ts_mean(f.close, 7) - f.close) + 20 * O.scale(
        O.correlation(f.vwap, O.delay(f.close, 5), 230)
    )


def _a033(f: Fields) -> pd.DataFrame:
    return O.rank(-((1 - (f.open / f.close)) ** 1))


def _a034(f: Fields) -> pd.DataFrame:
    return O.rank((1 - O.rank(O.stddev(f.returns, 2) / O.stddev(f.returns, 5))) + (1 - O.rank(O.delta(f.close, 1))))


def _a035(f: Fields) -> pd.DataFrame:
    return O.ts_rank(f.volume, 32) * (1 - O.ts_rank(f.close + f.high - f.low, 16)) * (1 - O.ts_rank(f.returns, 32))


def _a036(f: Fields) -> pd.DataFrame:
    return (
        2.21 * O.rank(O.correlation(f.close - f.open, O.delay(f.volume, 1), 15))
        + 0.7 * O.rank(f.open - f.close)
        + 0.73 * O.rank(O.ts_rank(O.delay(-f.returns, 6), 5))
        + O.rank(O.abs_(O.correlation(f.vwap, _adv(f, 20), 6)))
        + 0.6 * O.rank((O.ts_mean(f.close, 200) - f.open) * (f.close - f.open))
    )


def _a037(f: Fields) -> pd.DataFrame:
    return O.rank(O.correlation(O.delay(f.open - f.close, 1), f.close, 200)) + O.rank(f.open - f.close)


def _a038(f: Fields) -> pd.DataFrame:
    return (-O.rank(O.ts_rank(f.close, 10))) * O.rank(f.close / f.open)


def _a039(f: Fields) -> pd.DataFrame:
    return (-O.rank(O.delta(f.close, 7) * (1 - O.rank(O.decay_linear(f.volume / _adv(f, 20), 9))))) * (
        1 + O.rank(O.ts_sum(f.returns, 250))
    )


def _a040(f: Fields) -> pd.DataFrame:
    return (-O.rank(O.stddev(f.high, 10))) * O.correlation(f.high, f.volume, 10)


def _a041(f: Fields) -> pd.DataFrame:
    return (f.high * f.low) ** 0.5 - f.vwap


def _a042(f: Fields) -> pd.DataFrame:
    return O.rank(f.vwap - f.close) / O.rank(f.vwap + f.close)


def _a043(f: Fields) -> pd.DataFrame:
    return O.ts_rank(f.volume / _adv(f, 20), 20) * O.ts_rank(-O.delta(f.close, 7), 8)


def _a044(f: Fields) -> pd.DataFrame:
    return -O.correlation(f.high, O.rank(f.volume), 5)


def _a045(f: Fields) -> pd.DataFrame:
    return -(
        O.rank(O.ts_mean(O.delay(f.close, 5), 20))
        * O.correlation(f.close, f.volume, 2)
        * O.rank(O.correlation(O.ts_sum(f.close, 5), O.ts_sum(f.close, 20), 2))
    )


def _a046(f: Fields) -> pd.DataFrame:
    inner = ((O.delay(f.close, 20) - O.delay(f.close, 10)) / 10) - ((O.delay(f.close, 10) - f.close) / 10)
    return O.ternary(inner > 0.25, -1.0, O.ternary(inner < 0, 1.0, -(f.close - O.delay(f.close, 1))))


def _a047(f: Fields) -> pd.DataFrame:
    return (
        ((O.rank(1 / f.close) * f.volume) / _adv(f, 20))
        * ((f.high * O.rank(f.high - f.close)) / O.ts_mean(f.high, 5))
    ) - O.rank(f.vwap - O.delay(f.vwap, 5))


def _a049(f: Fields) -> pd.DataFrame:
    inner = ((O.delay(f.close, 20) - O.delay(f.close, 10)) / 10) - ((O.delay(f.close, 10) - f.close) / 10)
    return O.ternary(inner < -0.1, 1.0, -(f.close - O.delay(f.close, 1)))


def _a050(f: Fields) -> pd.DataFrame:
    return -O.ts_max(O.rank(O.correlation(O.rank(f.volume), O.rank(f.vwap), 5)), 5)


def _a051(f: Fields) -> pd.DataFrame:
    inner = ((O.delay(f.close, 20) - O.delay(f.close, 10)) / 10) - ((O.delay(f.close, 10) - f.close) / 10)
    return O.ternary(inner < -0.05, 1.0, -(f.close - O.delay(f.close, 1)))


def _a052(f: Fields) -> pd.DataFrame:
    return (
        (-O.ts_min(f.low, 5) + O.delay(O.ts_min(f.low, 5), 5))
        * O.rank((O.ts_sum(f.returns, 240) - O.ts_sum(f.returns, 20)) / 220)
        * O.ts_rank(f.volume, 5)
    )


def _a053(f: Fields) -> pd.DataFrame:
    denom = (f.close - f.low).replace(0, pd.NA)
    return -O.delta(((f.close - f.low) - (f.high - f.close)) / denom, 9)


def _a054(f: Fields) -> pd.DataFrame:
    return (-((f.low - f.close) * (f.open**5))) / ((f.low - f.high) * (f.close**5))


def _a055(f: Fields) -> pd.DataFrame:
    stoch = (f.close - O.ts_min(f.low, 12)) / (O.ts_max(f.high, 12) - O.ts_min(f.low, 12))
    return -O.correlation(O.rank(stoch), O.rank(f.volume), 6)


def _a057(f: Fields) -> pd.DataFrame:
    return -((f.close - f.vwap) / O.decay_linear(O.rank(O.ts_argmax(f.close, 30)), 2))


def _a060(f: Fields) -> pd.DataFrame:
    inner = ((f.close - f.low) - (f.high - f.close)) / (f.high - f.low) * f.volume
    return -(2 * O.scale(O.rank(inner)) - O.scale(O.rank(O.ts_argmax(f.close, 10))))


def _a061(f: Fields) -> pd.DataFrame:
    return (O.rank(f.vwap - O.ts_min(f.vwap, 16)) < O.rank(O.correlation(f.vwap, _adv(f, 180), 18))).astype(float)


def _a062(f: Fields) -> pd.DataFrame:
    left = O.rank(O.correlation(f.vwap, O.ts_sum(_adv(f, 20), 22), 10))
    right = O.rank((O.rank(f.open) + O.rank(f.open)) < (O.rank((f.high + f.low) / 2) + O.rank(f.high)))
    return (left < right).astype(float) * -1


def _a064(f: Fields) -> pd.DataFrame:
    left = O.rank(
        O.correlation(
            O.ts_sum(f.open * 0.178404 + f.low * (1 - 0.178404), 13),
            O.ts_sum(_adv(f, 120), 13),
            17,
        )
    )
    right = O.rank(O.delta(((f.high + f.low) / 2) * 0.178404 + f.vwap * (1 - 0.178404), 4))
    return (left < right).astype(float) * -1


def _a065(f: Fields) -> pd.DataFrame:
    left = O.rank(O.correlation(f.open * 0.00817205 + f.vwap * (1 - 0.00817205), O.ts_sum(_adv(f, 60), 9), 6))
    right = O.rank(f.open - O.ts_min(f.open, 14))
    return (left < right).astype(float) * -1


def _a066(f: Fields) -> pd.DataFrame:
    return (
        O.rank(O.decay_linear(O.delta(f.vwap, 4), 7))
        + O.ts_rank(
            O.decay_linear((f.low - f.vwap) / (f.open - (f.high + f.low) / 2), 11),
            7,
        )
    ) * -1


def _a068(f: Fields) -> pd.DataFrame:
    return (
        O.ts_rank(O.correlation(O.rank(f.high), O.rank(_adv(f, 15)), 9), 14)
        < O.rank(O.delta(f.close * 0.518371 + f.low * (1 - 0.518371), 1))
    ).astype(float) * -1


def _a071(f: Fields) -> pd.DataFrame:
    a = O.ts_rank(
        O.decay_linear(O.correlation(O.ts_rank(f.close, 3), O.ts_rank(_adv(f, 180), 12), 18), 4),
        16,
    )
    b = O.ts_rank(O.decay_linear((O.rank((f.low + f.open) - (f.vwap + f.vwap))) ** 2, 16), 4)
    return O.maximum(a, b)


def _a072(f: Fields) -> pd.DataFrame:
    num = O.rank(O.decay_linear(O.correlation((f.high + f.low) / 2, _adv(f, 40), 9), 10))
    den = O.rank(O.decay_linear(O.correlation(O.ts_rank(f.vwap, 4), O.ts_rank(f.volume, 19), 7), 3))
    return num / den


def _a073(f: Fields) -> pd.DataFrame:
    a = O.rank(O.decay_linear(O.delta(f.vwap, 5), 3))
    mix = f.open * 0.147155 + f.low * (1 - 0.147155)
    b = O.ts_rank(O.decay_linear((O.delta(mix, 2) / mix) * -1, 3), 17)
    return O.maximum(a, b) * -1


def _a074(f: Fields) -> pd.DataFrame:
    left = O.rank(O.correlation(f.close, O.ts_sum(_adv(f, 30), 37), 15))
    right = O.rank(
        O.correlation(O.rank(f.high * 0.0261661 + f.vwap * (1 - 0.0261661)), O.rank(f.volume), 11)
    )
    return (left < right).astype(float) * -1


def _a075(f: Fields) -> pd.DataFrame:
    return (O.rank(O.correlation(f.vwap, f.volume, 4)) < O.rank(O.correlation(O.rank(f.low), O.rank(_adv(f, 50)), 12))).astype(
        float
    )


def _a077(f: Fields) -> pd.DataFrame:
    a = O.rank(O.decay_linear(((((f.high + f.low) / 2) + f.high) - (f.vwap + f.high)), 20))
    b = O.rank(O.decay_linear(O.correlation(((f.high + f.low) / 2), _adv(f, 40), 3), 6))
    return O.minimum(a, b)


def _a078(f: Fields) -> pd.DataFrame:
    return O.rank(
        O.correlation(O.ts_sum(f.low * 0.352233 + f.vwap * (1 - 0.352233), 20), O.ts_sum(_adv(f, 40), 20), 7)
    ).pow(O.rank(O.correlation(O.rank(f.vwap), O.rank(f.volume), 6)))


def _a081(f: Fields) -> pd.DataFrame:
    left = O.rank(
        O.log(
            O.ts_product(
                O.rank((O.rank(O.correlation(f.vwap, O.ts_sum(_adv(f, 10), 50), 8))) ** 4),
                15,
            )
        )
    )
    right = O.rank(O.correlation(O.rank(f.vwap), O.rank(f.volume), 5))
    return (left < right).astype(float) * -1


def _a083(f: Fields) -> pd.DataFrame:
    hl = (f.high - f.low) / O.ts_mean(f.close, 5)
    return (O.rank(O.delay(hl, 2)) * O.rank(O.rank(f.volume))) / (hl / (f.vwap - f.close))


def _a084(f: Fields) -> pd.DataFrame:
    return O.signedpower(O.ts_rank(f.vwap - O.ts_max(f.vwap, 15), 21), O.delta(f.close, 5))


def _a085(f: Fields) -> pd.DataFrame:
    return O.rank(O.correlation((f.high * 0.876703 + f.close * (1 - 0.876703)), _adv(f, 30), 10)).pow(
        O.rank(O.correlation(O.ts_rank((f.high + f.low) / 2, 4), O.ts_rank(f.volume, 10), 7))
    )


def _a086(f: Fields) -> pd.DataFrame:
    ranked = O.ts_rank(O.correlation(f.close, O.ts_sum(_adv(f, 20), 15), 6), 20)
    return (ranked < O.rank(O.delta(f.close, 3))).astype(float) * -1


def _a088(f: Fields) -> pd.DataFrame:
    return O.minimum(
        O.rank(O.decay_linear(((O.rank(f.open) + O.rank(f.low)) - (O.rank(f.high) + O.rank(f.close))), 8)),
        O.ts_rank(O.decay_linear(O.correlation(O.ts_rank(f.close, 8), O.ts_rank(_adv(f, 60), 21), 8), 7), 3),
    )


def _a092(f: Fields) -> pd.DataFrame:
    a = O.ts_rank(
        O.decay_linear(((((f.high + f.low) / 2) + f.close) < (f.low + f.open)).astype(float), 15),
        19,
    )
    b = O.ts_rank(O.decay_linear(O.correlation(O.rank(f.low), O.rank(_adv(f, 30)), 8), 7), 7)
    return O.minimum(a, b)


def _a094(f: Fields) -> pd.DataFrame:
    return (
        O.rank(f.vwap - O.ts_min(f.vwap, 12)).pow(
            O.ts_rank(O.correlation(O.ts_rank(f.vwap, 20), O.ts_rank(_adv(f, 60), 4), 18), 3)
        )
        * -1
    )


def _a095(f: Fields) -> pd.DataFrame:
    return (
        O.rank(f.open - O.ts_min(f.open, 12))
        < O.ts_rank(O.rank(O.correlation(O.ts_sum((f.high + f.low) / 2, 19), O.ts_sum(_adv(f, 40), 19), 13)).pow(5), 12)
    ).astype(float)


def _a096(f: Fields) -> pd.DataFrame:
    a = O.ts_rank(O.decay_linear(O.correlation(O.rank(f.vwap), O.rank(f.volume), 4), 4), 8)
    b = O.ts_rank(O.decay_linear(O.ts_argmax(O.correlation(O.ts_rank(f.close, 7), O.ts_rank(_adv(f, 60), 4), 4), 13), 14), 13)
    return O.maximum(a, b) * -1


def _a098(f: Fields) -> pd.DataFrame:
    return O.rank(O.decay_linear(O.correlation(f.vwap, O.ts_sum(_adv(f, 5), 26), 5), 7)) - O.rank(
        O.decay_linear(O.ts_rank(O.ts_argmin(O.correlation(O.rank(f.open), O.rank(_adv(f, 15)), 21), 9), 7), 8)
    )


def _a099(f: Fields) -> pd.DataFrame:
    return (
        O.rank(O.correlation(O.ts_sum((f.high + f.low) / 2, 20), O.ts_sum(_adv(f, 60), 20), 9))
        < O.rank(O.correlation(f.low, f.volume, 6))
    ).astype(float) * -1


def _a101(f: Fields) -> pd.DataFrame:
    return (f.close - f.open) / ((f.high - f.low) + 0.001)


def _a048(f: Fields) -> pd.DataFrame:
    d1 = O.delta(f.close, 1)
    num = O.indneutralize(
        (O.correlation(d1, O.delta(O.delay(f.close, 1), 1), 250) * d1) / f.close,
        f.industry,
    )
    den = O.ts_sum((d1 / O.delay(f.close, 1)) ** 2, 250)
    return num / den


def _a056(f: Fields) -> pd.DataFrame:
    if f.cap is None:
        raise UnsupportedAlphaError("056", "requires cap")
    return -(
        O.rank(O.ts_sum(f.returns, 10) / O.ts_sum(O.ts_sum(f.returns, 2), 3)) * O.rank(f.returns * f.cap)
    )


def _a058(f: Fields) -> pd.DataFrame:
    return -O.ts_rank(O.decay_linear(O.correlation(O.indneutralize(f.vwap, f.industry), f.volume, 4), 8), 6)


def _a059(f: Fields) -> pd.DataFrame:
    mix = f.vwap * 0.728317 + f.vwap * (1 - 0.728317)
    return -O.ts_rank(O.decay_linear(O.correlation(O.indneutralize(mix, f.industry), f.volume, 4), 16), 8)


def _a063(f: Fields) -> pd.DataFrame:
    left = O.rank(O.decay_linear(O.delta(O.indneutralize(f.close, f.industry), 2), 8))
    mix = f.vwap * 0.318108 + f.open * (1 - 0.318108)
    right = O.rank(O.decay_linear(O.correlation(mix, O.ts_sum(_adv(f, 180), 37), 14), 12))
    return (left - right) * -1


def _a067(f: Fields) -> pd.DataFrame:
    return (
        O.rank(f.high - O.ts_min(f.high, 2)).pow(
            O.rank(O.correlation(O.indneutralize(f.vwap, f.industry), O.indneutralize(_adv(f, 20), f.industry), 6))
        )
        * -1
    )


def _a069(f: Fields) -> pd.DataFrame:
    return (
        O.rank(O.ts_max(O.delta(O.indneutralize(f.vwap, f.industry), 3), 5)).pow(
            O.ts_rank(O.correlation(f.close * 0.490655 + f.vwap * (1 - 0.490655), _adv(f, 20), 5), 9)
        )
        * -1
    )


def _a070(f: Fields) -> pd.DataFrame:
    return (
        O.rank(O.delta(f.vwap, 1)).pow(
            O.ts_rank(O.correlation(O.indneutralize(f.close, f.industry), _adv(f, 50), 18), 18)
        )
        * -1
    )


def _a076(f: Fields) -> pd.DataFrame:
    low_n = O.indneutralize(f.low, f.industry)
    a = O.rank(O.decay_linear(O.delta(f.vwap, 1), 12))
    b = O.ts_rank(O.decay_linear(O.delta(low_n, 1) / low_n, 15), 6)
    return O.maximum(a, b) * -1


def _a079(f: Fields) -> pd.DataFrame:
    mix = O.indneutralize(f.close * 0.60733 + f.open * (1 - 0.60733), f.industry)
    return O.rank(O.delta(mix, 1.2) / O.ts_min(mix, 4)) * O.rank(
        O.correlation(f.vwap, _adv(f, 150), 4)
    )


def _a080(f: Fields) -> pd.DataFrame:
    return (
        O.rank(O.sign(O.delta(O.indneutralize(f.open, f.industry), 1.5))).pow(
            O.ts_rank(O.correlation(f.high, _adv(f, 50), 4), 4)
        )
        * -1
    )


def _a082(f: Fields) -> pd.DataFrame:
    a = O.rank(O.decay_linear(O.delta(f.open, 1.4), 15))
    b = O.ts_rank(
        O.decay_linear(O.correlation(O.indneutralize(f.volume, f.industry), ((f.open * 0.634 + f.open * (1 - 0.634))), 17), 7),
        13,
    )
    return O.minimum(a, b) * -1


def _a087(f: Fields) -> pd.DataFrame:
    return (
        O.rank(O.decay_linear(O.delta(f.vwap, 4), 7))
        + O.ts_rank(
            O.decay_linear(((f.low * 0.9 + f.low * 0.1) - f.vwap) / (O.indneutralize(f.open, f.industry) - ((f.high + f.low) / 2)), 11),
            11,
        )
    ) * -1


def _a089(f: Fields) -> pd.DataFrame:
    return O.ts_rank(O.decay_linear(O.correlation(O.indneutralize(f.vwap, f.industry), _adv(f, 15), 5), 3), 3).pow(
        O.rank(O.decay_linear(O.delta(((f.close * 0.57) + (f.open * 0.43)), 3), 16))
    )


def _a090(f: Fields) -> pd.DataFrame:
    return O.rank(O.ts_rank(O.decay_linear(O.correlation(O.indneutralize(f.close, f.industry), _adv(f, 50), 8), 17), 18)) * -1


def _a091(f: Fields) -> pd.DataFrame:
    return (
        O.ts_rank(O.decay_linear(O.decay_linear(O.correlation(O.indneutralize(f.close, f.industry), f.volume, 10), 16), 4), 5)
        - O.rank(O.decay_linear(O.correlation(f.vwap, _adv(f, 30), 4), 3))
    )


def _a093(f: Fields) -> pd.DataFrame:
    return O.ts_rank(
        O.decay_linear(O.correlation(O.indneutralize(f.vwap, f.industry), _adv(f, 81), 17), 20),
        8,
    ).pow(O.rank(O.decay_linear(((f.close + f.open) / 2 - f.vwap), 18)))


def _a097(f: Fields) -> pd.DataFrame:
    return O.rank(O.decay_linear(O.delta(O.indneutralize(f.low, f.industry), 2), 8)).pow(
        O.ts_rank(O.decay_linear(O.correlation(O.rank(f.low), O.rank(_adv(f, 60)), 8), 6), 13)
    ) * -1


def _a100(f: Fields) -> pd.DataFrame:
    inner = O.indneutralize(
        ((O.correlation(f.close, O.ts_rank(_adv(f, 20), 5), 5) - O.rank(O.ts_argmin(f.close, 30))) * 1.0),
        f.industry,
    )
    return O.rank(inner) * -1


FORMULAS: dict[str, str] = {
    "001": "rank(Ts_ArgMax(SignedPower(((returns<0)?stddev(returns,20):close),2),5))-0.5",
    "002": "(-1 * correlation(rank(delta(log(volume),2)), rank((close-open)/open), 6))",
    "003": "(-1 * correlation(rank(open), rank(volume), 10))",
    "004": "(-1 * Ts_Rank(rank(low), 9))",
    "005": "rank(open - mean(vwap,10)) * (-1 * abs(rank(close-vwap)))",
    "006": "(-1 * correlation(open, volume, 10))",
    "007": "((adv20 < volume) ? ((-1 * ts_rank(abs(delta(close,7)),60))*sign(delta(close,7))) : -1)",
    "008": "(-1 * rank((sum(open,5)*sum(returns,5)) - delay(sum(open,5)*sum(returns,5),10)))",
    "009": "conditional delta(close,1) vs ts_min/ts_max window 5",
    "010": "rank of alpha#9-style delta with window 4",
    "011": "(rank(ts_max(vwap-close,3))+rank(ts_min(vwap-close,3)))*rank(delta(volume,3))",
    "012": "sign(delta(volume,1)) * (-1 * delta(close,1))",
    "013": "(-1 * rank(covariance(rank(close), rank(volume), 5)))",
    "014": "((-1 * rank(delta(returns,3))) * correlation(open, volume, 10))",
    "015": "(-1 * sum(rank(correlation(rank(high), rank(volume), 3)), 3))",
    "016": "(-1 * rank(covariance(rank(high), rank(volume), 5)))",
    "017": "((-1 * rank(ts_rank(close,10))) * rank(delta(delta(close,1),1))) * rank(ts_rank(volume/adv20,5))",
    "018": "(-1 * rank(stddev(abs(close-open),5) + (close-open) + correlation(close,open,10)))",
    "019": "((-1 * sign((close-delay(close,7))+delta(close,7))) * (1 + rank(1 + sum(returns,250))))",
    "020": "((-1 * rank(open-delay(high,1))) * rank(open-delay(close,1))) * rank(open-delay(low,1))",
    "021": "mean/std close vs volume/adv20 ternary",
    "022": "(-1 * (delta(correlation(high, volume, 5), 5) * rank(stddev(close, 20))))",
    "023": "((mean(high,20) < high) ? (-1 * delta(high,2)) : 0)",
    "024": "100-day mean break vs delta(close,3)",
    "025": "rank(((-1 * returns) * adv20 * vwap) * (high - close))",
    "026": "(-1 * ts_max(correlation(ts_rank(volume,5), ts_rank(high,5), 5), 3))",
    "027": "((0.5 < rank(mean(correlation(rank(volume), rank(vwap), 6), 2))) ? -1 : 1)",
    "028": "scale(correlation(adv20, low, 5) + ((high+low)/2) - close)",
    "029": "nested rank/scale/log product plus ts_rank of delayed returns",
    "030": "((1-rank(sign chain of close)) * sum(volume,5)) / sum(volume,20)",
    "031": "decay_linear ranks plus sign(scale(correlation(adv20, low, 12)))",
    "032": "scale(mean(close,7)-close) + 20*scale(correlation(vwap, delay(close,5), 230))",
    "033": "rank(-1 * ((1 - (open/close))^1))",
    "034": "rank((1-rank(stddev(returns,2)/stddev(returns,5))) + (1-rank(delta(close,1))))",
    "035": "Ts_Rank(volume,32) * (1-Ts_Rank(close+high-low,16)) * (1-Ts_Rank(returns,32))",
    "036": "weighted ranks of correlation/open-close/vwap/adv",
    "037": "rank(correlation(delay(open-close,1), close, 200)) + rank(open-close)",
    "038": "((-1 * rank(Ts_Rank(close,10))) * rank(close/open))",
    "039": "(-1 * rank(delta(close,7)*(1-rank(decay_linear(volume/adv20,9))))) * (1+rank(sum(returns,250)))",
    "040": "((-1 * rank(stddev(high,10))) * correlation(high, volume, 10))",
    "041": "(((high*low)^0.5) - vwap)",
    "042": "rank(vwap-close) / rank(vwap+close)",
    "043": "ts_rank(volume/adv20, 20) * ts_rank((-1 * delta(close,7)), 8)",
    "044": "(-1 * correlation(high, rank(volume), 5))",
    "045": "(-1 * ((rank(mean(delay(close,5),20)) * correlation(close,volume,2)) * rank(correlation(sum(close,5), sum(close,20), 2))))",
    "046": "10-day vs 20-day close slope ternary",
    "047": "rank(1/close)*volume/adv20 * high ranks minus rank(vwap delay)",
    "048": "IndNeutralize(...) / sum((delta(close,1)/delay(close,1))^2, 250)",
    "049": "slope < -0.1 ? 1 : -delta(close,1)",
    "050": "(-1 * ts_max(rank(correlation(rank(volume), rank(vwap), 5)), 5))",
    "051": "slope < -0.05 ? 1 : -delta(close,1)",
    "052": "((-ts_min(low,5)+delay(ts_min(low,5),5)) * rank((sum(returns,240)-sum(returns,20))/220)) * ts_rank(volume,5)",
    "053": "(-1 * delta(((close-low)-(high-close))/(close-low), 9))",
    "054": "((-1 * ((low-close)*(open^5))) / ((low-high)*(close^5)))",
    "055": "(-1 * correlation(rank((close-ts_min(low,12))/(ts_max(high,12)-ts_min(low,12))), rank(volume), 6))",
    "056": "-(rank(sum(returns,10)/sum(sum(returns,2),3)) * rank(returns * cap))",
    "057": "-( (close-vwap) / decay_linear(rank(ts_argmax(close,30)), 2) )",
    "058": "IndNeutralize(vwap, sector) vs volume",
    "059": "IndNeutralize(vwap, industry) vs volume",
    "060": "-(2*scale(rank((((close-low)-(high-close))/(high-low))*volume)) - scale(rank(ts_argmax(close,10))))",
    "061": "rank(vwap-ts_min(vwap,16)) < rank(correlation(vwap, adv180, 18))",
    "062": "(rank(correlation(vwap, sum(adv20,22), 10)) < rank(...open/high...)) * -1",
    "063": "IndNeutralize(close, industry)",
    "064": "correlation of mixed open/low vs adv120",
    "065": "correlation of mixed open/vwap vs adv60",
    "066": "decay_linear(delta(vwap)) + Ts_Rank(decay_linear((low-vwap)/(open-mid)))",
    "067": "IndNeutralize(vwap, sector)",
    "068": "Ts_Rank(correlation(rank(high), rank(adv15))) vs delta mixed close/low",
    "069": "IndNeutralize(vwap, industry)",
    "070": "IndNeutralize(close, industry)",
    "071": "max(Ts_Rank(decay_linear(correlation(ts_rank(close), ts_rank(adv180)))), Ts_Rank(decay_linear(rank(low+open-2*vwap)^2)))",
    "072": "rank(decay_linear(correlation(mid, adv40))) / rank(decay_linear(correlation(ts_rank(vwap), ts_rank(volume))))",
    "073": "max(rank(decay_linear(delta(vwap))), Ts_Rank(decay_linear(delta(mix)/mix))) * -1",
    "074": "rank(correlation(close, sum(adv30))) < rank(correlation(rank(mixed high/vwap), rank(volume)))",
    "075": "rank(correlation(vwap, volume)) < rank(correlation(rank(low), rank(adv50)))",
    "076": "IndNeutralize(low, industry)",
    "077": "min(rank(decay_linear(mid+high - vwap+high)), rank(decay_linear(correlation(mid, adv40))))",
    "078": "rank(correlation(sum(low/vwap mix), sum(adv40))) ^ rank(correlation(rank(vwap), rank(volume)))",
    "079": "IndNeutralize(close, industry)",
    "080": "IndNeutralize(open, industry)",
    "081": "rank(log(product(rank(rank(correlation(vwap,sum(adv10)))^4)))) < rank(correlation(rank(vwap), rank(volume)))",
    "082": "IndNeutralize(open, industry)",
    "083": "rank(delay((high-low)/mean(close,5),2))*rank(rank(volume)) / (((high-low)/mean(close,5))/(vwap-close))",
    "084": "SignedPower(ts_rank(vwap - ts_max(vwap,15), 21), delta(close,5))",
    "085": "rank(correlation(high/close mix, adv30))^rank(correlation(ts_rank(mid), ts_rank(volume)))",
    "086": "(Ts_Rank(correlation(close, sum(adv20,15)), 6) < rank(delta(close,3))) * -1",
    "087": "IndNeutralize(vwap, industry)",
    "088": "min(rank(decay_linear(rank(open)+rank(low)-rank(high)-rank(close))), Ts_Rank(decay_linear(correlation(ts_rank(close), ts_rank(adv60)))))",
    "089": "IndNeutralize(vwap, industry)",
    "090": "IndNeutralize(close, industry)",
    "091": "IndNeutralize(close, industry)",
    "092": "min(Ts_Rank(decay_linear((mid+close)<(low+open))), Ts_Rank(decay_linear(correlation(rank(low), rank(adv30)))))",
    "093": "IndNeutralize(vwap, industry)",
    "094": "rank(vwap-ts_min(vwap))^Ts_Rank(correlation(ts_rank(vwap), ts_rank(adv60))) * -1",
    "095": "rank(open-ts_min(open)) < Ts_Rank(rank(correlation(sum(mid), sum(adv40)))^5)",
    "096": "max(Ts_Rank(decay_linear(correlation(rank(vwap), rank(volume)))), Ts_Rank(decay_linear(ts_argmax(correlation(...))))) * -1",
    "097": "IndNeutralize(low, industry)",
    "098": "rank(decay_linear(correlation(vwap, sum(adv5)))) - rank(decay_linear(ts_rank(ts_argmin(correlation(rank(open), rank(adv15))))))",
    "099": "(rank(correlation(sum(mid), sum(adv60))) < rank(correlation(low, volume))) * -1",
    "100": "IndNeutralize(subindustry) * rank(coeff of variation of close)",
    "101": "(close - open) / ((high - low) + 0.001)",
}


_IMPL: dict[str, AlphaFn] = {
    "001": _a001,
    "002": _a002,
    "003": _a003,
    "004": _a004,
    "005": _a005,
    "006": _a006,
    "007": _a007,
    "008": _a008,
    "009": _a009,
    "010": _a010,
    "011": _a011,
    "012": _a012,
    "013": _a013,
    "014": _a014,
    "015": _a015,
    "016": _a016,
    "017": _a017,
    "018": _a018,
    "019": _a019,
    "020": _a020,
    "021": _a021,
    "022": _a022,
    "023": _a023,
    "024": _a024,
    "025": _a025,
    "026": _a026,
    "027": _a027,
    "028": _a028,
    "029": _a029,
    "030": _a030,
    "031": _a031,
    "032": _a032,
    "033": _a033,
    "034": _a034,
    "035": _a035,
    "036": _a036,
    "037": _a037,
    "038": _a038,
    "039": _a039,
    "040": _a040,
    "041": _a041,
    "042": _a042,
    "043": _a043,
    "044": _a044,
    "045": _a045,
    "046": _a046,
    "047": _a047,
    "048": _a048,
    "049": _a049,
    "050": _a050,
    "051": _a051,
    "052": _a052,
    "053": _a053,
    "054": _a054,
    "055": _a055,
    "056": _a056,
    "057": _a057,
    "058": _a058,
    "059": _a059,
    "060": _a060,
    "061": _a061,
    "062": _a062,
    "063": _a063,
    "064": _a064,
    "065": _a065,
    "066": _a066,
    "067": _a067,
    "068": _a068,
    "069": _a069,
    "070": _a070,
    "071": _a071,
    "072": _a072,
    "073": _a073,
    "074": _a074,
    "075": _a075,
    "076": _a076,
    "077": _a077,
    "078": _a078,
    "079": _a079,
    "080": _a080,
    "081": _a081,
    "082": _a082,
    "083": _a083,
    "084": _a084,
    "085": _a085,
    "086": _a086,
    "087": _a087,
    "088": _a088,
    "089": _a089,
    "090": _a090,
    "091": _a091,
    "092": _a092,
    "093": _a093,
    "094": _a094,
    "095": _a095,
    "096": _a096,
    "097": _a097,
    "098": _a098,
    "099": _a099,
    "100": _a100,
    "101": _a101,
}


def _all_ids() -> tuple[str, ...]:
    return tuple(f"{i:03d}" for i in range(1, 102))


def list_alphas() -> list[dict[str, object]]:
    rows = []
    for aid in _all_ids():
        rows.append(
            {
                "alpha_id": aid,
                "formula": FORMULAS.get(aid, ""),
                "supported": True,
                "requires_industry_or_cap": aid in INDUSTRY_OR_CAP,
            }
        )
    return rows


def supported_ids() -> tuple[str, ...]:
    return _all_ids()


def compute_alpha(alpha_id: str, panel: pd.DataFrame) -> pd.DataFrame:
    aid = str(alpha_id).strip().zfill(3)
    if aid not in {f"{i:03d}" for i in range(1, 102)}:
        raise KeyError(f"unknown alpha_id {alpha_id!r}")
    fn = _IMPL[aid]
    fields = Fields.from_panel(panel)
    try:
        return fn(fields)
    except UnsupportedOperatorError as exc:
        raise UnsupportedAlphaError(aid, str(exc)) from exc


def compute_spec(spec: FactorSpec, panel: pd.DataFrame) -> pd.DataFrame:
    if spec.padded_id() == "custom":
        raise UnsupportedAlphaError("custom", "expression plugin is not executed in-process")
    return compute_alpha(spec.padded_id(), panel)
