"""Equal-weight CN quality book with a single basket TSMOM overlay."""

from __future__ import annotations

from quantit.research.universes import CN_QUALITY
from quantit.strategy.hk_book import HKQualityBookStrategy


class CNQualityBookStrategy(HKQualityBookStrategy):
    """Equal-weight A-share operating blue chips; one skipped-lookback momentum signal.

    Rebalances each session. Residual weight stays cash (no CSI 300 ETF
    fallback). ``turnover_band`` skips names whose quantity change is too small
    to bother. Realized basket vol can only shrink the sleeve (no leverage).
    No shorting. Price only — quality labels pick the pool, not a scoring factor.
    """

    def __init__(
        self,
        lookback: int = 252,
        skip: int = 21,
        risk_off_scale: float = 0.5,
        invested_on: float = 0.95,
        turnover_band: float = 0.02,
        target_vol: float = 0.15,
        vol_lookback: int = 20,
        vol_floor: float = 0.05,
        universe: tuple[str, ...] | None = None,
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
        )
