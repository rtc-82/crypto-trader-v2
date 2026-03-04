import numpy as np


class UniverseSelector:

    def __init__(self, size=8):

        self.size = size

    def score_symbol(self, prices):

        if len(prices) < 20:
            return 0

        returns = np.diff(prices) / prices[:-1]

        momentum = prices[-1] / prices[0] - 1

        volatility = np.std(returns)

        score = abs(momentum) * 0.6 + volatility * 0.4

        return score

    def select(self, price_history):

        scores = {}

        for symbol, prices in price_history.items():

            score = self.score_symbol(prices)

            scores[symbol] = score

        ranked = sorted(scores, key=scores.get, reverse=True)

        return ranked[: self.size]