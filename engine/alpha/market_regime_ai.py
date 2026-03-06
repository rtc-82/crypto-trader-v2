import numpy as np


class MarketRegimeAI:

    def detect(self, prices):

        if len(prices) < 30:
            return "neutral"

        returns = np.diff(prices) / prices[:-1]

        volatility = np.std(returns)
        trend = np.mean(returns)

        if volatility > 0.035:
            return "crash"

        if abs(trend) > 0.002:
            return "trend"

        return "range"