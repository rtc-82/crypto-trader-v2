# execution/binance_candle_feed.py

import httpx
import asyncio
from datetime import datetime, timezone


class BinanceCandleFeed:
    """
    Fetches latest 5m SOLUSDT candle from Binance.
    Used ONLY for signal generation.
    """

    BASE_URL = "https://api.binance.com/api/v3/klines"

    def __init__(self, symbol="SOLUSDT", interval="5m"):
        self.symbol = symbol
        self.interval = interval
        self.last_open_time = None

    async def get_latest_closed_candle(self):
        """
        Returns most recently CLOSED candle.
        Binance returns the current forming candle last,
        so we take the second-to-last entry.
        """

        params = {
            "symbol": self.symbol,
            "interval": self.interval,
            "limit": 3
        }

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(self.BASE_URL, params=params)

        response.raise_for_status()
        data = response.json()

        if len(data) < 2:
            return None

        candle = data[-2]  # last closed candle

        open_time = candle[0]

        # Prevent duplicate processing
        if self.last_open_time == open_time:
            return None

        self.last_open_time = open_time

        return {
            "timestamp": datetime.fromtimestamp(open_time / 1000, tz=timezone.utc),
            "open": float(candle[1]),
            "high": float(candle[2]),
            "low": float(candle[3]),
            "close": float(candle[4]),
        }