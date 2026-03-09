from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np

from engine.core.signal import Signal


@dataclass(frozen=True)
class StrategyDecision:
    signal: Optional[Signal]
    reason: Optional[str]
    meta: dict[str, Any] = field(default_factory=dict)


class StrategyEngine:
    """
    Trend breakout engine that returns StrategyDecision
    so router logging stays consistent with mean reversion.
    """

    def __init__(self, config):
        self.ema_period = config["ema_period"]
        self.atr_period = config["atr_period"]
        self.slope_threshold = config["slope_threshold"]
        self.vol_percentile_threshold = config["volatility_percentile_threshold"]
        self.breakout_lookback = config.get("breakout_lookback", 25)

        self.multiplier = 2 / (self.ema_period + 1)
        self.ema_value = None
        self.ema_history = deque(maxlen=50)

        self.prev_close = None
        self.tr_queue = deque(maxlen=self.atr_period)
        self.current_atr = None
        self.atr_history = deque(maxlen=5000)

        self.previous_slope = 0.0

        self.high_window = deque(maxlen=self.breakout_lookback)
        self.low_window = deque(maxlen=self.breakout_lookback)

    def _decision(self, signal=None, reason=None, **meta):
        return StrategyDecision(signal=signal, reason=reason, meta=meta)

    def generate_signal(self, price, high=None, low=None, timestamp=None):
        base_meta = {
            "price": float(price),
            "high": float(high) if high is not None else None,
            "low": float(low) if low is not None else None,
            "timestamp": timestamp,
            "ema_period": int(self.ema_period),
            "atr_period": int(self.atr_period),
            "slope_threshold": float(self.slope_threshold),
            "vol_threshold": float(self.vol_percentile_threshold),
            "breakout_lookback": int(self.breakout_lookback),
            "ema_history_len": len(self.ema_history),
            "atr_history_len": len(self.atr_history),
            "tr_queue_len": len(self.tr_queue),
        }

        if high is None or low is None:
            return self._decision(reason="missing_high_low", **base_meta)

        if high < low:
            return self._decision(reason="invalid_ohlc_range", **base_meta)

        prior_high_break = None
        prior_low_break = None

        if len(self.high_window) == self.high_window.maxlen:
            prior_high_break = max(self.high_window)

        if len(self.low_window) == self.low_window.maxlen:
            prior_low_break = min(self.low_window)

        if self.ema_value is None:
            self.ema_value = price
        else:
            self.ema_value = ((price - self.ema_value) * self.multiplier) + self.ema_value

        self.ema_history.append(self.ema_value)
        self.high_window.append(high)
        self.low_window.append(low)

        base_meta["ema_history_len"] = len(self.ema_history)
        base_meta["ema"] = float(self.ema_value)

        if len(self.ema_history) < 50:
            self.prev_close = price
            return self._decision(reason="ema_history_warmup", **base_meta)

        raw_slope = self.ema_history[-1] - self.ema_history[0]
        base_meta["raw_slope"] = float(raw_slope)

        if self.prev_close is None:
            self.prev_close = price
            return self._decision(reason="prev_close_not_initialized", **base_meta)

        tr1 = high - low
        tr2 = abs(high - self.prev_close)
        tr3 = abs(low - self.prev_close)
        true_range = max(tr1, tr2, tr3)
        self.tr_queue.append(true_range)

        base_meta["true_range"] = float(true_range)
        base_meta["tr_queue_len"] = len(self.tr_queue)

        if len(self.tr_queue) < self.atr_period:
            self.prev_close = price
            return self._decision(reason="atr_warmup", **base_meta)

        self.current_atr = float(np.mean(self.tr_queue))
        self.atr_history.append(self.current_atr)
        self.prev_close = price

        base_meta["atr"] = float(self.current_atr)
        base_meta["atr_history_len"] = len(self.atr_history)

        if not np.isfinite(self.current_atr):
            return self._decision(reason="atr_non_finite", **base_meta)

        if self.current_atr <= 0:
            return self._decision(reason="atr_non_positive", **base_meta)

        if len(self.atr_history) < 100:
            return self._decision(reason="atr_history_warmup", **base_meta)

        slope = raw_slope / self.current_atr

        atr_array = np.array(self.atr_history, dtype=float)
        vol_percentile = float(np.mean(atr_array < self.current_atr))

        base_meta["slope_norm"] = float(slope)
        base_meta["vol_percentile"] = float(vol_percentile)
        base_meta["breakout_high"] = float(prior_high_break) if prior_high_break is not None else None
        base_meta["breakout_low"] = float(prior_low_break) if prior_low_break is not None else None
        base_meta["previous_slope"] = float(self.previous_slope)

        if vol_percentile < self.vol_percentile_threshold:
            self.previous_slope = slope
            return self._decision(reason="volatility_below_threshold", **base_meta)

        if prior_high_break is None or prior_low_break is None:
            self.previous_slope = slope
            return self._decision(reason="breakout_window_warmup", **base_meta)

        breakout_distance = 0.0

        if slope > 0 and self.current_atr > 0:
            breakout_distance = (price - prior_high_break) / self.current_atr
        elif slope < 0 and self.current_atr > 0:
            breakout_distance = (prior_low_break - price) / self.current_atr

        base_meta["breakout_distance"] = float(breakout_distance)

        if (
            self.previous_slope <= self.slope_threshold
            and slope > self.slope_threshold
            and price > prior_high_break
        ):
            self.previous_slope = slope
            return self._decision(
                signal=Signal(direction="LONG", atr=float(self.current_atr)),
                reason="trend_long_breakout",
                **base_meta,
            )

        if (
            self.previous_slope >= -self.slope_threshold
            and slope < -self.slope_threshold
            and price < prior_low_break
        ):
            self.previous_slope = slope
            return self._decision(
                signal=Signal(direction="SHORT", atr=float(self.current_atr)),
                reason="trend_short_breakout",
                **base_meta,
            )

        self.previous_slope = slope
        return self._decision(reason="breakout_not_confirmed", **base_meta)