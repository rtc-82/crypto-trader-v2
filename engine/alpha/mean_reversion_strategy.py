from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Optional

import numpy as np

from engine.core.signal import Signal


@dataclass(frozen=True)
class StrategyDecision:
    signal: Optional[Signal]
    reason: Optional[str]
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class MRConfig:
    bb_period: int = 40
    z_entry: float = 1.6
    z_exit: float = 0.4
    atr_period: int = 14
    min_atr_history: int = 120
    max_atr_percentile_for_mr: float = 0.55  # only mean-revert when vol isn't too high


class MeanReversionStrategy:
    """
    Simple compression-market mean reversion:
    - Bollinger / z-score entry
    - ATR percentile filter to avoid mean reversion in very high vol

    Returns StrategyDecision so the caller can inspect no-signal reasons.
    """

    def __init__(self, cfg: MRConfig | None = None) -> None:
        self.cfg = cfg or MRConfig()
        self._closes: Deque[float] = deque(maxlen=self.cfg.bb_period)

        self._prev_close: Optional[float] = None
        self._tr_q: Deque[float] = deque(maxlen=self.cfg.atr_period)
        self._atr_hist: Deque[float] = deque(maxlen=3000)
        self._atr: Optional[float] = None

    def _decision(
        self,
        signal: Optional[Signal],
        reason: Optional[str],
        base_meta: dict[str, Any],
        **extra_meta: Any,
    ) -> StrategyDecision:
        meta = dict(base_meta)
        meta.update(extra_meta)
        return StrategyDecision(signal=signal, reason=reason, meta=meta)

    def _update_atr(self, close: float, high: float, low: float) -> Optional[float]:
        if self._prev_close is None:
            self._prev_close = close
            return None

        tr1 = high - low
        tr2 = abs(high - self._prev_close)
        tr3 = abs(low - self._prev_close)
        tr = max(tr1, tr2, tr3)

        if not np.isfinite(tr):
            self._prev_close = close
            return None

        self._tr_q.append(float(tr))

        if len(self._tr_q) < self.cfg.atr_period:
            self._prev_close = close
            return None

        atr = float(np.mean(self._tr_q))
        if not np.isfinite(atr):
            self._prev_close = close
            return None

        self._atr = atr
        self._atr_hist.append(self._atr)
        self._prev_close = close
        return self._atr

    def on_candle(self, close: float, high: float, low: float, timestamp=None) -> StrategyDecision:
        close = float(close)
        high = float(high)
        low = float(low)

        base_meta = {
            "close": close,
            "high": high,
            "low": low,
            "bb_period": int(self.cfg.bb_period),
            "atr_period": int(self.cfg.atr_period),
            "z_entry": float(self.cfg.z_entry),
            "z_exit": float(self.cfg.z_exit),
            "min_atr_history": int(self.cfg.min_atr_history),
            "max_atr_percentile_for_mr": float(self.cfg.max_atr_percentile_for_mr),
            "close_history_len": len(self._closes),
            "atr_history_len": len(self._atr_hist),
            "atr": float(self._atr) if self._atr is not None else None,
            "timestamp": timestamp,
        }

        if not (np.isfinite(close) and np.isfinite(high) and np.isfinite(low)):
            return self._decision(
                signal=None,
                reason="non_finite_ohlc",
                base_meta=base_meta,
            )

        if high < low:
            return self._decision(
                signal=None,
                reason="invalid_ohlc_range",
                base_meta=base_meta,
            )

        self._closes.append(close)
        atr = self._update_atr(close, high, low)

        base_meta["close_history_len"] = len(self._closes)
        base_meta["atr_history_len"] = len(self._atr_hist)
        base_meta["atr"] = float(atr) if atr is not None else None

        if len(self._closes) < self.cfg.bb_period:
            return self._decision(
                signal=None,
                reason="insufficient_close_history",
                base_meta=base_meta,
            )

        if atr is None:
            return self._decision(
                signal=None,
                reason="atr_not_ready",
                base_meta=base_meta,
            )

        if not np.isfinite(atr):
            return self._decision(
                signal=None,
                reason="atr_non_finite",
                base_meta=base_meta,
            )

        if atr <= 0:
            return self._decision(
                signal=None,
                reason="atr_non_positive",
                base_meta=base_meta,
            )

        if len(self._atr_hist) < self.cfg.min_atr_history:
            return self._decision(
                signal=None,
                reason="insufficient_atr_history",
                base_meta=base_meta,
            )

        atr_arr = np.array(self._atr_hist, dtype=float)
        if atr_arr.size == 0 or not np.all(np.isfinite(atr_arr)):
            return self._decision(
                signal=None,
                reason="invalid_atr_history",
                base_meta=base_meta,
            )

        atr_pct = float(np.mean(atr_arr < atr))

        if not np.isfinite(atr_pct):
            return self._decision(
                signal=None,
                reason="atr_percentile_invalid",
                base_meta=base_meta,
            )

        if atr_pct > self.cfg.max_atr_percentile_for_mr:
            return self._decision(
                signal=None,
                reason="atr_percentile_too_high",
                base_meta=base_meta,
                atr_percentile=atr_pct,
            )

        arr = np.array(self._closes, dtype=float)
        if arr.size < self.cfg.bb_period or not np.all(np.isfinite(arr)):
            return self._decision(
                signal=None,
                reason="invalid_close_history",
                base_meta=base_meta,
                atr_percentile=atr_pct,
            )

        mean = float(arr.mean())
        std = float(arr.std(ddof=0))

        if not np.isfinite(mean) or not np.isfinite(std):
            return self._decision(
                signal=None,
                reason="mean_or_std_non_finite",
                base_meta=base_meta,
                atr_percentile=atr_pct,
            )

        if std <= 0:
            return self._decision(
                signal=None,
                reason="std_non_positive",
                base_meta=base_meta,
                atr_percentile=atr_pct,
                mean=mean,
                std=std,
            )

        z = float((close - mean) / std)

        if not np.isfinite(z):
            return self._decision(
                signal=None,
                reason="zscore_non_finite",
                base_meta=base_meta,
                atr_percentile=atr_pct,
                mean=mean,
                std=std,
            )

        if z >= self.cfg.z_entry:
            return self._decision(
                signal=Signal(direction="SHORT", atr=float(atr)),
                reason=None,
                base_meta=base_meta,
                atr_percentile=atr_pct,
                mean=mean,
                std=std,
                zscore=z,
            )

        if z <= -self.cfg.z_entry:
            return self._decision(
                signal=Signal(direction="LONG", atr=float(atr)),
                reason=None,
                base_meta=base_meta,
                atr_percentile=atr_pct,
                mean=mean,
                std=std,
                zscore=z,
            )

        return self._decision(
            signal=None,
            reason="zscore_not_extreme_enough",
            base_meta=base_meta,
            atr_percentile=atr_pct,
            mean=mean,
            std=std,
            zscore=z,
        )