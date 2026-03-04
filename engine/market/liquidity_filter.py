import requests


class LiquidityFilter:

    def __init__(self, config):

        self.min_volume = config["min_volume_usdt"]

        self.max_spread = config["max_spread_pct"]

    def check(self, symbol):

        try:

            url = "https://api.binance.com/api/v3/ticker/bookTicker"

            params = {"symbol": symbol}

            r = requests.get(url, params=params, timeout=5)

            data = r.json()

            bid = float(data["bidPrice"])
            ask = float(data["askPrice"])

            spread = (ask - bid) / bid

            if spread > self.max_spread:
                return False

            vol_url = "https://api.binance.com/api/v3/ticker/24hr"

            r = requests.get(vol_url, params={"symbol": symbol}, timeout=5)

            vol_data = r.json()

            volume = float(vol_data["quoteVolume"])

            if volume < self.min_volume:
                return False

            return True

        except Exception:

            return False