from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Optional

import numpy as np


@dataclass(frozen=True)
class RegimeResult:
    regime: str  # "TRENDING" | "COMPRESSION" | "NEUTRAL"
    atr: Optional[float]
    slope_norm: Optional[float]
    vol_percentile: Optional[float]
    reason: Optional[str] = None
    meta: dict[str, Any] = field(default_factory=dict)


class MarketRegimeEngine:
    """
    Regime classifier using:
    - EMA slope normalized by ATR (trend strength)
    - ATR percentile (volatility context)

    Outputs:
      TRENDING: strong normalized EMA slope AND volatility not extremely low
      COMPRESSION: volatility is low (ATR percentile under threshold)
      NEUTRAL: otherwise

    This version keeps the same architecture but adds structured diagnostics
    through RegimeResult.reason and RegimeResult.meta.
    """

    def __init__(
        self,
        ema_period: int = 50,
        atr_period: int = 14,
        slope_lookback: int = 10,
        trend_slope_threshold: float = 0.35,
        compression_vol_percentile: float = 0.35,
        trend_min_vol_percentile: float = 0.50,
        atr_history_len: int = 1500,
    ) -> None:
        self.ema_period = ema_period
        self.atr_period = atr_period
        self.slope_lookback = slope_lookback
        self.trend_slope_threshold = trend_slope_threshold
        self.compression_vol_percentile = compression_vol_percentile
        self.trend_min_vol_percentile = trend_min_vol_percentile

        self._ema_mult = 2.0 / (ema_period + 1)
        self._ema: Optional[float] = None
        self._ema_hist: Deque[float] = deque(maxlen=max(ema_period * 2, slope_lookback + 5))

        self._prev_close: Optional[float] = None
        self._tr_q: Deque[float] = deque(maxlen=atr_period)
        self._atr_hist: Deque[float] = deque(maxlen=atr_history_len)
        self._atr: Optional[float] = None

    def _base_meta(self, close: float, high: float, low: float) -> dict[str, Any]:
        return {
            "close": float(close),
            "high": float(high),
            "low": float(low),
            "ema_period": int(self.ema_period),
            "atr_period": int(self.atr_period),
            "slope_lookback": int(self.slope_lookback),
            "trend_slope_threshold": float(self.trend_slope_threshold),
            "compression_vol_percentile": float(self.compression_vol_percentile),
            "trend_min_vol_percentile": float(self.trend_min_vol_percentile),
            "ema_hist_len": len(self._ema_hist),
            "atr_hist_len": len(self._atr_hist),
            "tr_queue_len": len(self._tr_q),
            "atr": float(self._atr) if self._atr is not None else None,
            "ema": float(self._ema) if self._ema is not None else None,
        }

    def update(self, close: float, high: float, low: float) -> RegimeResult:
        # EMA update
        if self._ema is None:
            self._ema = close
        else:
            self._ema = (close - self._ema) * self._ema_mult + self._ema
        self._ema_hist.append(float(self._ema))

        base_meta = self._base_meta(close, high, low)

        # ATR update
        if self._prev_close is None:
            self._prev_close = close
            return RegimeResult(
                regime="NEUTRAL",
                atr=None,
                slope_norm=None,
                vol_percentile=None,
                reason="prev_close_not_initialized",
                meta=base_meta,
            )

        tr1 = high - low
        tr2 = abs(high - self._prev_close)
        tr3 = abs(low - self._prev_close)
        tr = max(tr1, tr2, tr3)
        self._tr_q.append(float(tr))

        base_meta["true_range"] = float(tr)

        if len(self._tr_q) < self.atr_period:
            self._prev_close = close
            base_meta["tr_queue_len"] = len(self._tr_q)
            return RegimeResult(
                regime="NEUTRAL",
                atr=None,
                slope_norm=None,
                vol_percentile=None,
                reason="atr_warmup",
                meta=base_meta,
            )

        self._atr = float(np.mean(self._tr_q))
        self._atr_hist.append(self._atr)
        self._prev_close = close

        base_meta["atr"] = float(self._atr)
        base_meta["atr_hist_len"] = len(self._atr_hist)

        if self._atr <= 0:
            return RegimeResult(
                regime="NEUTRAL",
                atr=self._atr,
                slope_norm=None,
                vol_percentile=None,
                reason="atr_non_positive",
                meta=base_meta,
            )

        if len(self._atr_hist) < 100:
            return RegimeResult(
                regime="NEUTRAL",
                atr=self._atr,
                slope_norm=None,
                vol_percentile=None,
                reason="atr_history_warmup",
                meta=base_meta,
            )

        if len(self._ema_hist) < (self.slope_lookback + 2):
            return RegimeResult(
                regime="NEUTRAL",
                atr=self._atr,
                slope_norm=None,
                vol_percentile=None,
                reason="ema_history_warmup",
                meta=base_meta,
            )

        # Normalized slope
        ema_now = self._ema_hist[-1]
        ema_then = self._ema_hist[-1 - self.slope_lookback]
        slope_norm = float((ema_now - ema_then) / self._atr)

        # Vol percentile
        atr_arr = np.array(self._atr_hist, dtype=float)
        vol_pct = float(np.mean(atr_arr < self._atr))

        base_meta["ema_now"] = float(ema_now)
        base_meta["ema_then"] = float(ema_then)
        base_meta["slope_norm"] = float(slope_norm)
        base_meta["vol_percentile"] = float(vol_pct)

        # Classify
        if vol_pct <= self.compression_vol_percentile:
            return RegimeResult(
                regime="COMPRESSION",
                atr=self._atr,
                slope_norm=slope_norm,
                vol_percentile=vol_pct,
                reason="low_volatility_compression",
                meta=base_meta,
            )

        if abs(slope_norm) >= self.trend_slope_threshold and vol_pct >= self.trend_min_vol_percentile:
            return RegimeResult(
                regime="TRENDING",
                atr=self._atr,
                slope_norm=slope_norm,
                vol_percentile=vol_pct,
                reason="trend_thresholds_passed",
                meta=base_meta,
            )

        if abs(slope_norm) < self.trend_slope_threshold and vol_pct < self.trend_min_vol_percentile:
            reason = "slope_below_trend_and_vol_below_trend_floor"
        elif abs(slope_norm) < self.trend_slope_threshold:
            reason = "slope_below_trend_threshold"
        elif vol_pct < self.trend_min_vol_percentile:
            reason = "vol_below_trend_floor"
        else:
            reason = "neutral_fallback"

        return RegimeResult(
            regime="NEUTRAL",
            atr=self._atr,
            slope_norm=slope_norm,
            vol_percentile=vol_pct,
            reason=reason,
            meta=base_meta,
        )