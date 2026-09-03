"""Equal-weight CN quality book with a single basket TSMOM overlay."""

from __future__ import annotations

from quantit.research.universes import CN_QUALITY
from quantit.strategy.hk_book import HKQualityBookStrategy


class CNQualityBookStrategy(HKQualityBookStrategy):
    """Equal-weight A-share operating blue chips; one skipped-lookback momentum signal.

    Rebalances on the last session of each month. Residual weight stays cash
    (no CSI 300 ETF fallback). No shorting. Price only — quality labels pick
    the pool, not a scoring factor.
    """

    def __init__(
        self,
        lookback: int = 252,
        skip: int = 21,
        risk_off_scale: float = 0.5,
        invested_on: float = 0.95,
        turnover_band: float = 0.02,
        universe: tuple[str, ...] | None = None,
    ) -> None:
        super().__init__(
            lookback=lookback,
            skip=skip,
            risk_off_scale=risk_off_scale,
            invested_on=invested_on,
            turnover_band=turnover_band,
            universe=universe if universe is not None else CN_QUALITY,
        )
