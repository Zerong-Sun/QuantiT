"""Equal-weight CN quality book with a single basket TSMOM overlay."""

from __future__ import annotations

from quantit.research.universes import CN_QUALITY
from quantit.strategy.hk_book import HKQualityBookStrategy


class CNQualityBookStrategy(HKQualityBookStrategy):
    """A-share operating blue chips; one skipped-lookback momentum signal.

    Typical book ~90% invested; 95% only when basket momentum is strong.
    Default ``target_vol=0.30`` matches the book's ~20% realized vol.
    Dual momentum inside the sleeve. Residual is cash, not 510300.SS.
    """

    def __init__(
        self,
        lookback: int = 252,
        skip: int = 21,
        risk_off_scale: float = 0.70,
        invested_on: float = 0.90,
        turnover_band: float = 0.02,
        target_vol: float = 0.30,
        vol_lookback: int = 20,
        vol_floor: float = 0.05,
        universe: tuple[str, ...] | None = None,
        weighting: str = "dual_mom",
        max_leverage: float = 1.5,
        invested_strong: float = 0.95,
        strong_mom: float = 0.20,
    ) -> None:
        super().__init__(
            lookback=lookback,
            skip=skip,
            risk_off_scale=risk_off_scale,
            invested_on=invested_on,
            turnover_band=turnover_band,
            target_vol=target_vol,
            vol_lookback=vol_lookback,
            vol_floor=vol_floor,
            universe=universe if universe is not None else CN_QUALITY,
            weighting=weighting,
            max_leverage=max_leverage,
            invested_strong=invested_strong,
            strong_mom=strong_mom,
        )
