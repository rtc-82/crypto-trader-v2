import asyncio
import json
import websockets


class BinanceWSFeed:

    def __init__(self, symbol, interval="1m"):

        self.symbol = symbol.lower()
        self.interval = interval

        self.url = f"wss://stream.binance.com:9443/ws/{self.symbol}@kline_{interval}"

        self.latest_candle = None

    async def connect(self):

        while True:

            try:

                async with websockets.connect(self.url) as ws:

                    async for msg in ws:

                        data = json.loads(msg)

                        k = data["k"]

                        if k["x"]:  # candle closed

                            self.latest_candle = {
                                "close": float(k["c"]),
                                "high": float(k["h"]),
                                "low": float(k["l"]),
                                "close_time": int(k["T"])
                            }

            except Exception:
                await asyncio.sleep(1)

    async def get_latest_closed_candle(self):

        return self.latest_candle