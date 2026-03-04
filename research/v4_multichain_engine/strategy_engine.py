from collections import deque
import numpy as np
from research.v4_multichain_engine.models.signal import Signal


class StrategyEngine:
    """
    Clean Trend Breakout Engine (5m)

    Components:
    - EMA slope transition (normalized by ATR)
    - Volatility percentile filter
    - Structural breakout confirmation (recent high/low break)
    """

    def __init__(self, config):

        self.ema_period = config["ema_period"]
        self.atr_period = config["atr_period"]
        self.slope_threshold = config["slope_threshold"]
        self.vol_percentile_threshold = config["volatility_percentile_threshold"]

        self.breakout_lookback = config.get("breakout_lookback", 25)

        # EMA
        self.multiplier = 2 / (self.ema_period + 1)
        self.ema_value = None
        self.ema_history = deque(maxlen=50)

        # ATR
        self.prev_close = None
        self.tr_queue = deque(maxlen=self.atr_period)
        self.current_atr = None
        self.atr_history = deque(maxlen=5000)

        # Slope memory
        self.previous_slope = 0.0

        # Structure breakout windows
        self.high_window = deque(maxlen=self.breakout_lookback)
        self.low_window = deque(maxlen=self.breakout_lookback)

    # ==========================================================

    def generate_signal(self, price, high=None, low=None, timestamp=None):

        if high is None or low is None:
            return None

        # Compute breakout levels BEFORE adding current bar
        prior_high_break = None
        prior_low_break = None

        if len(self.high_window) == self.high_window.maxlen:
            prior_high_break = max(self.high_window)

        if len(self.low_window) == self.low_window.maxlen:
            prior_low_break = min(self.low_window)

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

        # Append current structure
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
            return None

        if prior_high_break is None or prior_low_break is None:
            return None

        # ==============================
        # Breakout Logic
        # ==============================

        signal = None

        # LONG
        if (
            self.previous_slope <= self.slope_threshold
            and slope > self.slope_threshold
            and price > prior_high_break
        ):
            signal = Signal(direction="LONG", atr=float(self.current_atr))

        # SHORT
        elif (
            self.previous_slope >= -self.slope_threshold
            and slope < -self.slope_threshold
            and price < prior_low_break
        ):
            signal = Signal(direction="SHORT", atr=float(self.current_atr))

        self.previous_slope = slope
        return signal