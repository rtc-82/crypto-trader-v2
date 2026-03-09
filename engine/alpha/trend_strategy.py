from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from engine.core.strategy_engine import StrategyEngine
from engine.core.signal import Signal


@dataclass(frozen=True)
class StrategyDecision:
    signal: Optional[Signal]
    reason: Optional[str]
    meta: dict[str, Any] = field(default_factory=dict)


class TrendStrategy:
    """
    Wrapper around the trend strategy engine.
    Normalizes return values into StrategyDecision.
    """

    def __init__(self, config: dict):
        self.strategy = StrategyEngine(config)

    def on_candle(
        self,
        price: float,
        high: float,
        low: float,
        timestamp=None
    ) -> StrategyDecision:
        result = self.strategy.generate_signal(
            price,
            high,
            low,
            timestamp,
        )

        # New engine path: already returns StrategyDecision-like object
        if hasattr(result, "signal") and hasattr(result, "reason") and hasattr(result, "meta"):
            return StrategyDecision(
                signal=result.signal,
                reason=result.reason,
                meta=result.meta or {},
            )

        # Old engine path: returns raw Signal or None
        if result is None:
            return StrategyDecision(
                signal=None,
                reason="trend_no_signal",
                meta={
                    "price": float(price),
                    "high": float(high),
                    "low": float(low),
                },
            )

        return StrategyDecision(
            signal=result,
            reason=None,
            meta={
                "price": float(price),
                "high": float(high),
                "low": float(low),
            },
        )