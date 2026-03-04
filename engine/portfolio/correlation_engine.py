import numpy as np
import logging

logger = logging.getLogger("trading_engine")


class CorrelationEngine:

    def __init__(self, threshold=0.9, window=200):

        self.threshold = threshold
        self.window = window
        self.price_history = {}

    # -------------------------------------

    def update_price(self, symbol, price):

        if symbol not in self.price_history:

            self.price_history[symbol] = []

        self.price_history[symbol].append(price)

        if len(self.price_history[symbol]) > self.window:

            self.price_history[symbol].pop(0)

    # -------------------------------------

    def correlation(self, symbol_a, symbol_b):

        a = self.price_history.get(symbol_a)
        b = self.price_history.get(symbol_b)

        if not a or not b:
            return 0

        if len(a) < 20 or len(b) < 20:
            return 0

        a = np.array(a[-self.window:])
        b = np.array(b[-self.window:])

        return np.corrcoef(a, b)[0][1]

    # -------------------------------------

    def is_correlated(self, symbol, open_symbols):

        for s in open_symbols:

            corr = self.correlation(symbol, s)

            if abs(corr) > self.threshold:

                logger.info(
                    f"[CORRELATION] {symbol} highly correlated with {s} ({corr:.2f})"
                )

                return True

        return False