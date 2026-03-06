class SignalStrength:

    def __init__(self):

        self.min_scale = 0.7
        self.max_scale = 1.5

    def scale(self, signal):

        try:

            atr = getattr(signal, "atr", None)

            strength = getattr(signal, "strength", None)

            if strength is not None:

                return max(self.min_scale, min(self.max_scale, strength))

            if atr:

                scale = atr / 100

                return max(self.min_scale, min(self.max_scale, scale))

        except Exception:
            pass

        return 1.0