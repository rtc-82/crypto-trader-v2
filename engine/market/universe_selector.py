import numpy as np


class UniverseSelector:

    def __init__(self, size=8, momentum_window=20, vol_window=20):

        self.size = size
        self.momentum_window = momentum_window
        self.vol_window = vol_window

    def score_symbol(self, prices):

        if len(prices) < max(self.momentum_window, self.vol_window) + 1:
            return 0

        prices = np.array(prices)

        returns = np.diff(prices) / prices[:-1]

        momentum = prices[-1] / prices[-self.momentum_window] - 1

        volatility = np.std(returns[-self.vol_window:])

        score = abs(momentum) * 0.6 + volatility * 0.4

        return score

    def select(self, price_history):

        scores = {}

        for symbol, prices in price_history.items():

            score = self.score_symbol(prices)

            scores[symbol] = score

        ranked = sorted(scores, key=scores.get, reverse=True)

        return ranked[: self.size]