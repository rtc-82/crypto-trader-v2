import requests
import logging

logger = logging.getLogger("trading_engine")

BINANCE_24HR = "https://api.binance.com/api/v3/ticker/24hr"


class UniverseSelector:
    """
    Selects the most liquid Binance USDT pairs.

    Filters by:
    - USDT pairs
    - Minimum volume
    - Top N by volume
    """

    def __init__(self, min_volume=50_000_000, max_symbols=25):

        self.min_volume = min_volume
        self.max_symbols = max_symbols

    def get_universe(self):

        try:

            r = requests.get(BINANCE_24HR, timeout=10)
            data = r.json()

        except Exception as e:

            logger.error(f"[UNIVERSE] Binance request failed: {e}")
            return []

        symbols = []

        for s in data:

            symbol = s["symbol"]

            if not symbol.endswith("USDT"):
                continue

            try:
                volume = float(s["quoteVolume"])
            except:
                continue

            if volume < self.min_volume:
                continue

            symbols.append((symbol, volume))

        symbols.sort(key=lambda x: x[1], reverse=True)

        universe = [s[0] for s in symbols[:self.max_symbols]]

        logger.info(f"[UNIVERSE] Selected {len(universe)} symbols")

        return universe