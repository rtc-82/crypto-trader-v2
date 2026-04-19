from collections import deque
from typing import Optional
import numpy as np

from engine.core.signal import Signal


class StrategyEngine:
    """
    Clean Trend Breakout Engine (5m)

    Components:
    - EMA slope transition (normalized by ATR)
    - Volatility percentile filter
    - Structural breakout confirmation
    """

    def __init__(self, config: dict):

        self.ema_period = config.get("ema_period", 50)
        self.atr_period = config.get("atr_period", 14)
        self.slope_threshold = config.get("slope_threshold", 0.4)
        self.vol_percentile_threshold = config.get("volatility_percentile_threshold", 0.7)
        self.breakout_lookback = config.get("breakout_lookback", 20)

        # EMA
        self.multiplier = 2 / (self.ema_period + 1)
        self.ema_value: Optional[float] = None
        self.ema_history = deque(maxlen=50)

        # ATR
        self.prev_close: Optional[float] = None
        self.tr_queue = deque(maxlen=self.atr_period)
        self.current_atr: Optional[float] = None
        self.atr_history = deque(maxlen=5000)

        # Slope memory
        self.previous_slope = 0.0

        # Breakout windows
        self.high_window = deque(maxlen=self.breakout_lookback)
        self.low_window = deque(maxlen=self.breakout_lookback)

    def to_snapshot(self) -> dict:
        return {
            "ema_value": self.ema_value,
            "ema_history": list(self.ema_history),
            "prev_close": self.prev_close,
            "tr_queue": list(self.tr_queue),
            "current_atr": self.current_atr,
            "atr_history": list(self.atr_history),
            "previous_slope": self.previous_slope,
            "high_window": list(self.high_window),
            "low_window": list(self.low_window),
        }

    def from_snapshot(self, snap: dict) -> None:
        if not isinstance(snap, dict):
            return

        ema_value = snap.get("ema_value")
        self.ema_value = float(ema_value) if ema_value is not None else None

        self.ema_history.clear()
        for x in snap.get("ema_history", []):
            self.ema_history.append(float(x))

        prev_close = snap.get("prev_close")
        self.prev_close = float(prev_close) if prev_close is not None else None

        self.tr_queue.clear()
        for x in snap.get("tr_queue", []):
            self.tr_queue.append(float(x))

        current_atr = snap.get("current_atr")
        self.current_atr = float(current_atr) if current_atr is not None else None

        self.atr_history.clear()
        for x in snap.get("atr_history", []):
            self.atr_history.append(float(x))

        previous_slope = snap.get("previous_slope")
        self.previous_slope = float(previous_slope) if previous_slope is not None else 0.0

        self.high_window.clear()
        for x in snap.get("high_window", []):
            self.high_window.append(float(x))

        self.low_window.clear()
        for x in snap.get("low_window", []):
            self.low_window.append(float(x))

    # ==========================================================

    def generate_signal(
        self,
        price: float,
        high: float,
        low: float,
        timestamp=None,
    ) -> Optional[Signal]:

        if high is None or low is None:
            return None

        # --- Breakout reference BEFORE adding current candle ---
        prior_high_break = max(self.high_window) if len(self.high_window) == self.high_window.maxlen else None
        prior_low_break = min(self.low_window) if len(self.low_window) == self.low_window.maxlen else None

        # ==============================
        # EMA
        # ==============================

        if self.ema_value is None:
            self.ema_value = price
        else:
            self.ema_value = (
                (price - self.ema_value) * self.multiplier
                + self.ema_value
            )

        self.ema_history.append(self.ema_value)

        # Append structure AFTER breakout reference
        self.high_window.append(high)
        self.low_window.append(low)

        if len(self.ema_history) < 50:
            self.prev_close = price
            return None

        raw_slope = self.ema_history[-1] - self.ema_history[0]

        # ==============================
        # ATR
        # ==============================

        if self.prev_close is None:
            self.prev_close = price
            return None

        tr1 = high - low
        tr2 = abs(high - self.prev_close)
        tr3 = abs(low - self.prev_close)

        true_range = max(tr1, tr2, tr3)
        self.tr_queue.append(true_range)

        if len(self.tr_queue) < self.atr_period:
            self.prev_close = price
            return None

        self.current_atr = float(np.mean(self.tr_queue))
        self.atr_history.append(self.current_atr)

        self.prev_close = price

        # ==============================
        # Filters
        # ==============================

        if self.current_atr == 0:
            return None

        if len(self.atr_history) < 100:
            return None

        slope = raw_slope / self.current_atr

        atr_array = np.array(self.atr_history, dtype=float)
        vol_percentile = float(np.mean(atr_array < self.current_atr))

        if vol_percentile < self.vol_percentile_threshold:
            self.previous_slope = slope
            return None

        if prior_high_break is None or prior_low_break is None:
            self.previous_slope = slope
            return None

        # ==============================
        # Breakout Logic
        # ==============================

        signal = None

        # LONG
        if (
            slope > self.slope_threshold
            and price > prior_high_break
        ):
            signal = Signal(direction="LONG", atr=float(self.current_atr))

        # SHORT
        elif (
            slope < -self.slope_threshold
            and price < prior_low_break
        ):
            signal = Signal(direction="SHORT", atr=float(self.current_atr))

        self.previous_slope = slope
        return signal