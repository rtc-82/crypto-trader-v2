from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from engine.core.signal import Signal
from engine.alpha.market_regime_engine import MarketRegimeEngine, RegimeResult
from engine.alpha.trend_strategy import TrendStrategy
from engine.alpha.mean_reversion_strategy import MeanReversionStrategy, MRConfig


@dataclass(frozen=True)
class RouterOutput:
    regime: str
    regime_meta: RegimeResult
    signal: Optional[Signal]
    strategy_used: str  # "trend" | "mean_reversion" | "none"
    reason: Optional[str] = None
    meta: dict[str, Any] = field(default_factory=dict)


class RegimeRouter:
    """
    TRENDING -> TrendStrategy
    COMPRESSION -> MeanReversionStrategy
    NEUTRAL -> no signal

    Returns RouterOutput with signal + reason + metadata for diagnostics.
    """

    def __init__(
        self,
        trend_config: dict,
        regime_engine: MarketRegimeEngine | None = None,
        mr_config: MRConfig | None = None,
    ) -> None:
        self.regime_engine = regime_engine or MarketRegimeEngine(
            ema_period=trend_config.get("ema_period", 50),
            atr_period=trend_config.get("atr_period", 14),
        )
        self.trend = TrendStrategy(trend_config)
        self.mean_rev = MeanReversionStrategy(mr_config)

        self.last_regime: Optional[str] = None

    def on_candle(self, close: float, high: float, low: float, timestamp=None) -> RouterOutput:
        regime_meta = self.regime_engine.update(close, high, low)
        regime = regime_meta.regime
        self.last_regime = regime

        shared_meta = {
            "close": float(close),
            "high": float(high),
            "low": float(low),
        }

        if regime == "TRENDING":
            decision = self.trend.on_candle(close, high, low, timestamp)
            return RouterOutput(
                regime=regime,
                regime_meta=regime_meta,
                signal=decision.signal,
                strategy_used="trend",
                reason=decision.reason,
                meta={**shared_meta, **decision.meta},
            )

        if regime == "COMPRESSION":
            decision = self.mean_rev.on_candle(close, high, low, timestamp)
            return RouterOutput(
                regime=regime,
                regime_meta=regime_meta,
                signal=decision.signal,
                strategy_used="mean_reversion",
                reason=decision.reason,
                meta={**shared_meta, **decision.meta},
            )

        return RouterOutput(
            regime=regime,
            regime_meta=regime_meta,
            signal=None,
            strategy_used="none",
            reason="regime_neutral",
            meta=shared_meta,
        )