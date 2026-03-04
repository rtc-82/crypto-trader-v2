import numpy as np


class VolatilitySelector:

    def __init__(self, max_symbols=6, lookback=20):
        self.max_symbols = max_symbols
        self.lookback = lookback
        self.prices = {}

    def update(self, symbol, price):

        if symbol not in self.prices:
            self.prices[symbol] = []

        self.prices[symbol].append(price)

        if len(self.prices[symbol]) > self.lookback:
            self.prices[symbol].pop(0)

    def top_symbols(self):

        vols = {}

        for s, p in self.prices.items():

            if len(p) < 5:
                continue

            returns = np.diff(p) / p[:-1]

            vols[s] = np.std(returns)

        ranked = sorted(vols, key=vols.get, reverse=True)

        return ranked[:self.max_symbols]