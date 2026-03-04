import asyncio
import os
import time
import logging
import requests
import numpy as np

from dotenv import load_dotenv

from engine.config.config import (
    STRATEGY_CONFIG,
    ENGINE_CONFIG,
    GLOBAL_RISK_CONFIG,
    POSITION_CONFIG,
    UNIVERSE_CONFIG
)

from engine.config.symbols import SYMBOLS
from engine.config.symbol_routes import SYMBOL_ROUTES

from engine.market.universe_selector import UniverseSelector
from engine.analytics.trade_attribution import TradeAttribution

from engine.core.risk_manager import RiskManager
from engine.core.capital_accounting import CapitalAccounting
from engine.core.position_manager import PositionManager
from engine.core.exit_manager import ExitManager
from engine.core.trade_logger import TradeLogger

from engine.data.binance_feed import BinanceCandleFeed
from engine.utils.telegram_controller import TelegramController

from engine.alpha.regime_router import RegimeRouter
from engine.alpha.signal_ranker import rank_signals

from engine.portfolio.live_allocator import LivePortfolioAllocator
from engine.portfolio.correlation_engine import CorrelationEngine
from engine.portfolio.global_risk_engine import GlobalRiskEngine

logger = logging.getLogger("trading_engine")

load_dotenv()


class MultiChainOrchestrator:

    def __init__(self, executors, symbol, interval, loop_interval, initial_equity, max_drawdown):

        self.executors = executors
        self.interval = interval
        self.loop_interval = loop_interval
        self.max_drawdown = max_drawdown

        logger.info("Multi-market trading engine starting")

        self.symbols = SYMBOLS

        self.last_processed_candle = {}

        self.price_history = {}

        self.volatility_symbols = 6

        self.feed_semaphore = asyncio.Semaphore(10)

        # ----------------------------
        # Dynamic Universe
        # ----------------------------

        self.universe_selector = UniverseSelector(
            size=UNIVERSE_CONFIG["universe_size"]
        )

        self.active_universe = SYMBOLS
        self.last_universe_update = 0

        # ----------------------------
        # Trade Attribution
        # ----------------------------

        self.attribution = TradeAttribution()

        # ----------------------------
        # Telegram
        # ----------------------------

        self.telegram_token = os.getenv("TELEGRAM_TOKEN")
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")

        self.telegram_controller = TelegramController(
            self.telegram_token,
            self.telegram_chat_id
        )

        # ----------------------------

        self.daily_start_equity = None

        self.router = RegimeRouter(trend_config=STRATEGY_CONFIG)

        self.global_risk = GlobalRiskEngine(
            max_daily_loss_pct=GLOBAL_RISK_CONFIG["max_daily_loss_pct"],
            max_trade_fraction=GLOBAL_RISK_CONFIG["max_trade_fraction"],
            max_trades_per_hour=GLOBAL_RISK_CONFIG["max_trades_per_hour"],
        )

        self.risk = RiskManager({
            "risk_per_trade": ENGINE_CONFIG["portfolio_base_risk_pct"],
            "max_position_size": 0.25,
        })

        self.position_manager = PositionManager(
            max_concurrent_positions=POSITION_CONFIG["max_concurrent_positions"]
        )

        self.exit_manager = ExitManager()

        self.trade_logger = TradeLogger()

        self.trade_ids = {}

        self.allocator = LivePortfolioAllocator(ENGINE_CONFIG)

        self.correlation = CorrelationEngine(
            threshold=ENGINE_CONFIG["correlation_threshold"],
            window=ENGINE_CONFIG["correlation_lookback_bars"]
        )

        chains = list(executors.keys())

        self.capital = CapitalAccounting(
            initial_equity=initial_equity,
            chains=chains,
        )

        self.feeds = {}

        for s in self.symbols:
            logger.info(f"[FEED] Creating feed for {s}")
            self.feeds[s] = BinanceCandleFeed(s, interval)

    # ------------------------------------------------
    # TELEGRAM
    # ------------------------------------------------

    def send_telegram(self, message):

        if not self.telegram_token or not self.telegram_chat_id:
            return

        try:

            url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"

            requests.post(
                url,
                json={"chat_id": self.telegram_chat_id, "text": message},
                timeout=5
            )

        except Exception as e:
            logger.error(f"Telegram error: {e}")

    # ------------------------------------------------
    # VOLATILITY
    # ------------------------------------------------

    def update_volatility(self, symbol, price):

        history = self.price_history.setdefault(symbol, [])

        history.append(price)

        if len(history) > 50:
            history.pop(0)

    def get_top_symbols(self):

        vols = {}

        for s, prices in self.price_history.items():

            if len(prices) < 10:
                continue

            returns = np.diff(prices) / prices[:-1]

            vols[s] = float(np.std(returns))

        ranked = sorted(vols, key=vols.get, reverse=True)

        return ranked[:self.volatility_symbols]

    # ------------------------------------------------
    # VOLATILITY SCALER
    # ------------------------------------------------

    def volatility_scaler(self, symbol):

        prices = self.price_history.get(symbol)

        if not prices or len(prices) < 10:
            return 1.0

        returns = np.diff(prices) / prices[:-1]

        vol = np.std(returns)

        target_vol = 0.02

        scaler = target_vol / max(vol, 1e-6)

        return max(0.5, min(1.5, scaler))

    # ------------------------------------------------
    # FETCH CANDLE
    # ------------------------------------------------

    async def fetch_candle(self, symbol, feed):

        async with self.feed_semaphore:

            try:

                candle = await feed.get_latest_closed_candle()

                return symbol, candle

            except Exception as e:

                logger.error(f"[FEED ERROR] {symbol}: {e}")

                return symbol, None

    # ------------------------------------------------
    # WARMUP
    # ------------------------------------------------

    async def warmup(self):

        logger.info("[WARMUP] starting")

        async def load_symbol(symbol, feed):

            try:

                candles = await feed.get_historical_candles(200)

                for c in candles:

                    price = c["close"]

                    self.router.on_candle(
                        price,
                        c["high"],
                        c["low"],
                        c.get("close_time")
                    )

                    self.update_volatility(symbol, price)

                    self.correlation.update_price(symbol, price)

            except Exception as e:

                logger.error(f"[WARMUP ERROR] {symbol}: {e}")

        await asyncio.gather(*[
            load_symbol(symbol, feed)
            for symbol, feed in self.feeds.items()
        ])

        logger.info("[WARMUP] complete")

    # ------------------------------------------------
    # EXIT MANAGEMENT
    # ------------------------------------------------

    async def check_exits(self, latest_prices):

        for position in self.position_manager.all_positions():

            symbol = position.symbol

            price = latest_prices.get(symbol)

            if price is None:
                continue

            decision = self.exit_manager.evaluate_exit(
                position.direction,
                position.entry_price,
                price,
                position.atr
            )

            if not decision.should_exit:
                continue

            logger.info(f"[EXIT] {symbol}")

            async def close_chain(chain):

                executor = self.executors[chain]

                return await executor.close_position(symbol)

            await asyncio.gather(*[
                close_chain(c) for c in self.executors
            ])

            # Attribution logging
            r = self.position_manager.r_multiple(
                position.entry_price,
                price,
                position.stop_loss,
                position.direction
            )

            regime = getattr(position, "regime", "unknown")

            self.attribution.record(symbol, regime, r)

            self.position_manager.close_position(symbol)

            self.send_telegram(f"📉 Closed {symbol} R={round(r,2)}")

    # ------------------------------------------------
    # MAIN LOOP
    # ------------------------------------------------

    async def run(self):

        logger.info("Multi-chain engine started.")

        await self.warmup()

        loop_counter = 0

        while True:

            loop_start = time.time()

            if os.path.exists("kill.switch"):
                logger.warning("Kill switch detected.")
                return

            balances = await asyncio.gather(*[
                executor.get_balance()
                for executor in self.executors.values()
            ])

            equity = sum(balances)

            logger.info(f"[PORTFOLIO] Equity={equity:.2f}")

            if self.daily_start_equity is None:

                self.daily_start_equity = equity

                self.global_risk.reset_daily_baseline(equity)

            results = await asyncio.gather(*[
                self.fetch_candle(symbol, feed)
                for symbol, feed in self.feeds.items()
            ])

            latest_prices = {}

            for symbol, candle in results:

                if not candle:
                    continue

                price = candle["close"]

                latest_prices[symbol] = price

                self.update_volatility(symbol, price)

                self.correlation.update_price(symbol, price)

            await self.check_exits(latest_prices)

            # Universe refresh

            refresh_seconds = UNIVERSE_CONFIG["refresh_interval_minutes"] * 60

            if time.time() - self.last_universe_update > refresh_seconds:

                self.active_universe = self.universe_selector.select(self.price_history)

                self.last_universe_update = time.time()

                logger.info(f"[UNIVERSE] {self.active_universe}")

            active_symbols = self.get_top_symbols()

            candidates = []

            for symbol, candle in results:

                if not candle:
                    continue

                if symbol not in self.active_universe:
                    continue

                close_time = candle["close_time"]

                if self.last_processed_candle.get(symbol) == close_time:
                    continue

                self.last_processed_candle[symbol] = close_time

                price = candle["close"]

                if active_symbols and symbol not in active_symbols:
                    continue

                out = self.router.on_candle(
                    price,
                    candle["high"],
                    candle["low"],
                    close_time
                )

                if out.signal:

                    candidates.append({
                        "symbol": symbol,
                        "signal": out.signal,
                        "meta": getattr(out, "regime_meta", {}),
                        "price": price
                    })

            if not candidates:

                logger.info("[SCAN] no signals")

                await asyncio.sleep(self.loop_interval)

                continue

            best = rank_signals(
                candidates,
                correlation_engine=self.correlation,
                open_symbols=self.position_manager.open_symbols()
            )

            if not best:
                continue

            symbol = best.symbol
            direction = best.signal.direction
            atr = best.signal.atr

            price = next(
                (c["price"] for c in candidates if c["symbol"] == symbol),
                None
            )

            if price is None:
                continue

            if not self.global_risk.allow_new_trade(equity):
                logger.info("[RISK] blocked")
                continue

            base_size = self.risk.calculate_position_size(
                equity,
                price,
                atr
            )

            allowed, multiplier = self.allocator.allow_entry(
                equity,
                self.position_manager.open_positions_count()
            )

            if not allowed:
                continue

            vol_scale = self.volatility_scaler(symbol)

            size = base_size * multiplier * vol_scale

            if size <= 0:
                continue

            routes = SYMBOL_ROUTES.get(symbol, {})

            executable_chains = [
                chain for chain in self.executors
                if routes.get(chain) is not None
            ]

            if not executable_chains:
                continue

            chain_size = size / len(executable_chains)

            async def execute_chain(chain):

                executor = self.executors[chain]

                token = routes.get(chain)

                return await executor.execute_trade(
                    symbol=token,
                    direction=direction,
                    size=chain_size
                )

            results = await asyncio.gather(*[
                execute_chain(c) for c in executable_chains
            ])

            success = any(r and getattr(r, "success", False) for r in results)

            if success:

                logger.info(f"[TRADE OPENED] {symbol}")

                self.position_manager.open_position(
                    symbol=symbol,
                    direction=direction,
                    entry_price=price,
                    size=size,
                    atr=atr,
                    entry_ts=int(time.time())
                )

                self.send_telegram(f"🚀 Trade Opened {symbol} {direction}")

            # Attribution summary every 50 loops

            loop_counter += 1

            if loop_counter % 50 == 0:

                logger.info(f"[ATTRIBUTION] {self.attribution.summary()}")

            logger.info(f"[LOOP] duration={time.time() - loop_start:.3f}s")

            await asyncio.sleep(self.loop_interval)