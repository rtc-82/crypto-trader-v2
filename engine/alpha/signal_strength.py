class SignalStrength:
    def __init__(self):
        self.min_scale = 0.7
        self.max_scale = 1.5

    def _clamp(self, value: float) -> float:
        return max(self.min_scale, min(self.max_scale, float(value)))

    def scale(self, signal, meta=None):
        try:
            strength = getattr(signal, "strength", None)
            if strength is not None:
                return self._clamp(strength)

            meta = meta or {}

            zscore = abs(float(meta.get("zscore", 0.0))) if meta.get("zscore") is not None else 0.0
            z_entry = float(meta.get("z_entry", 1.0) or 1.0)

            slope_norm = abs(float(meta.get("slope_norm", 0.0))) if meta.get("slope_norm") is not None else 0.0
            slope_threshold = float(meta.get("slope_threshold", 1.0) or 1.0)

            breakout_distance = abs(float(meta.get("breakout_distance", 0.0))) if meta.get("breakout_distance") is not None else 0.0
            vol_percentile = float(meta.get("vol_percentile", 0.0) or 0.0)

            mr_component = min(zscore / max(z_entry, 1e-9), 2.0)
            trend_component = min(slope_norm / max(slope_threshold, 1e-9), 2.0)
            breakout_component = min(breakout_distance, 2.0)

            raw = (
                0.40 * mr_component +
                0.30 * trend_component +
                0.20 * breakout_component +
                0.10 * vol_percentile
            )

            scale = 0.7 + raw * 0.4
            return self._clamp(scale)

        except Exception:
            return 1.0