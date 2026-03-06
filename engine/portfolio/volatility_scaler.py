import numpy as np


class VolatilityScaler:

    def __init__(self, target_vol=0.02, lookback=20):

        self.target_vol = target_vol
        self.lookback = lookback

    def scale(self, prices):

        if len(prices) < self.lookback + 1:
            return 1.0

        prices = np.array(prices)

        returns = np.diff(prices) / prices[:-1]

        vol = np.std(returns[-self.lookback:])

        if vol == 0:
            return 1.0

        scale = self.target_vol / vol

        return max(0.5, min(scale, 2.0))