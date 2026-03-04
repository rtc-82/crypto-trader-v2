from __future__ import annotations

import logging
import requests


class BinanceCandleFeed:
    """
    Fetches the latest CLOSED candle only.
    """
    def __init__(self, symbol: str, interval: str, logger: logging.Logger):
        self.symbol = symbol
        self.interval = interval
        self.logger = logger
        self.last_close_time = None

    def get_latest_closed_candle(self) -> dict | None:
        url = "https://api.binance.com/api/v3/klines"
        params = {"symbol": self.symbol, "interval": self.interval, "limit": 3}
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        klines = r.json()

        # The last element can be still-forming; use the previous one as "closed"
        closed = klines[-2]
        open_time = int(closed[0])
        close_time = int(closed[6])

        if self.last_close_time == close_time:
            return None

        self.last_close_time = close_time

        return {
            "open_time": open_time,
            "close_time": close_time,
            "open": float(closed[1]),
            "high": float(closed[2]),
            "low": float(closed[3]),
            "close": float(closed[4]),
            "volume": float(closed[5]),
        }