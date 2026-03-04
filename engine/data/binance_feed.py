import aiohttp
import asyncio


class BinanceCandleFeed:

    BASE_URL = "https://api.binance.com/api/v3/klines"

    def __init__(self, symbol, interval):

        self.symbol = symbol
        self.interval = interval

    async def get_latest_closed_candle(self):

        params = {
            "symbol": self.symbol,
            "interval": self.interval,
            "limit": 2
        }

        async with aiohttp.ClientSession() as session:

            async with session.get(self.BASE_URL, params=params) as resp:

                data = await resp.json()

        candle = data[-2]

        return {
            "open": float(candle[1]),
            "high": float(candle[2]),
            "low": float(candle[3]),
            "close": float(candle[4]),
            "close_time": candle[6]
        }

    async def get_historical_candles(self, limit=200):

        params = {
            "symbol": self.symbol,
            "interval": self.interval,
            "limit": limit
        }

        async with aiohttp.ClientSession() as session:

            async with session.get(self.BASE_URL, params=params) as resp:

                data = await resp.json()

        candles = []

        for c in data:

            candles.append({
                "open": float(c[1]),
                "high": float(c[2]),
                "low": float(c[3]),
                "close": float(c[4]),
                "close_time": c[6]
            })

        return candles