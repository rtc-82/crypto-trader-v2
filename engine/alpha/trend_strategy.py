from __future__ import annotations

from typing import Optional

from engine.core.strategy_engine import StrategyEngine
from engine.core.signal import Signal


class TrendStrategy:
    """
    Wrapper around your existing StrategyEngine.
    Used when the market regime = TRENDING.
    """

    def __init__(self, config: dict):
        self.strategy = StrategyEngine(config)

    def on_candle(
        self,
        price: float,
        high: float,
        low: float,
        timestamp=None
    ) -> Optional[Signal]:

        return self.strategy.generate_signal(
            price,
            high,
            low,
            timestamp,
        )