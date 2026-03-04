from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, Optional

import numpy as np


@dataclass(frozen=True)
class RegimeResult:
    regime: str  # "TRENDING" | "COMPRESSION" | "NEUTRAL"
    atr: Optional[float]
    slope_norm: Optional[float]
    vol_percentile: Optional[float]


class MarketRegimeEngine:
    """
    Regime classifier using:
    - EMA slope normalized by ATR (trend strength)
    - ATR percentile (volatility context)

    Outputs:
      TRENDING: strong normalized EMA slope AND volatility not extremely low
      COMPRESSION: volatility is low (ATR percentile under threshold)
      NEUTRAL: otherwise
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

    def update(self, close: float, high: float, low: float) -> RegimeResult:
        # EMA update
        if self._ema is None:
            self._ema = close
        else:
            self._ema = (close - self._ema) * self._ema_mult + self._ema
        self._ema_hist.append(float(self._ema))

        # ATR update
        if self._prev_close is None:
            self._prev_close = close
            return RegimeResult("NEUTRAL", None, None, None)

        tr1 = high - low
        tr2 = abs(high - self._prev_close)
        tr3 = abs(low - self._prev_close)
        tr = max(tr1, tr2, tr3)
        self._tr_q.append(float(tr))

        if len(self._tr_q) < self.atr_period:
            self._prev_close = close
            return RegimeResult("NEUTRAL", None, None, None)

        self._atr = float(np.mean(self._tr_q))
        self._atr_hist.append(self._atr)
        self._prev_close = close

        if self._atr <= 0 or len(self._atr_hist) < 100 or len(self._ema_hist) < (self.slope_lookback + 2):
            return RegimeResult("NEUTRAL", self._atr, None, None)

        # Normalized slope
        ema_now = self._ema_hist[-1]
        ema_then = self._ema_hist[-1 - self.slope_lookback]
        slope_norm = float((ema_now - ema_then) / self._atr)

        # Vol percentile
        atr_arr = np.array(self._atr_hist, dtype=float)
        vol_pct = float(np.mean(atr_arr < self._atr))

        # Classify
        if vol_pct <= self.compression_vol_percentile:
            regime = "COMPRESSION"
        elif abs(slope_norm) >= self.trend_slope_threshold and vol_pct >= self.trend_min_vol_percentile:
            regime = "TRENDING"
        else:
            regime = "NEUTRAL"

        return RegimeResult(regime, self._atr, slope_norm, vol_pct)