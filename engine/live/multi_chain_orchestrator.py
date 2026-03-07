import asyncio
import os
import time
import logging
import requests
from datetime import datetime
from typing import Dict, Any, Tuple, List, Optional

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

from engine.tools.performance_report import PerformanceReport

from engine.data.binance_feed import BinanceCandleFeed
from engine.utils.telegram_controller import TelegramController

from engine.alpha.regime_router import RegimeRouter
from engine.alpha.signal_ranker import rank_signals
from engine.alpha.signal_strength import SignalStrength

from engine.portfolio.live_allocator import LivePortfolioAllocator
from engine.portfolio.correlation_engine import CorrelationEngine
from engine.portfolio.global_risk_engine import GlobalRiskEngine
from engine.portfolio.volatility_scaler import VolatilityScaler

logger = logging.getLogger("trading_engine")
load_dotenv()

try:
    from engine.market.liquidity_filter import LiquidityFilter
except Exception:
    LiquidityFilter = None


class MultiChainOrchestrator:

    def __init__(self, executors, symbol, interval, loop_interval, initial_equity, max_drawdown):

        logger.info("Multi-market trading engine starting")

        self.executors = executors
        self.interval = interval
        self.loop_interval = loop_interval
        self.max_drawdown = max_drawdown

        # keep constructor compatibility; runtime still uses configured symbols
        self.symbols = SYMBOLS

        self.last_processed_candle: Dict[str, Any] = {}
        self.price_history: Dict[str, list] = {}

        self.feed_semaphore = asyncio.Semaphore(10)

        self.universe_selector = UniverseSelector(size=UNIVERSE_CONFIG["universe_size"])
        self.last_universe_refresh = 0
        self.universe_refresh_sec = UNIVERSE_CONFIG["refresh_interval_minutes"] * 60
        self.active_universe = self.symbols

        self.attribution = TradeAttribution()

        # one independent router per symbol to avoid cross-symbol state contamination
        self.routers: Dict[str, RegimeRouter] = {
            s: RegimeRouter(trend_config=STRATEGY_CONFIG)
            for s in self.symbols
        }

        self.signal_strength = SignalStrength()
        self.vol_scaler = VolatilityScaler()

        self.global_risk = GlobalRiskEngine(
            max_daily_loss_pct=GLOBAL_RISK_CONFIG["max_daily_loss_pct"],
            max_trade_fraction=GLOBAL_RISK_CONFIG["max_trade_fraction"],
            max_trades_per_hour=GLOBAL_RISK_CONFIG["max_trades_per_hour"]
        )

        self.risk = RiskManager({
            "risk_per_trade": ENGINE_CONFIG["portfolio_base_risk_pct"],
            "max_position_size": 0.25
        })

        self.position_manager = PositionManager(
            max_concurrent_positions=POSITION_CONFIG["max_concurrent_positions"]
        )

        self.exit_manager = ExitManager()
        self.trade_logger = TradeLogger()
        self.performance = PerformanceReport()

        self.allocator = LivePortfolioAllocator(ENGINE_CONFIG)

        self.correlation = CorrelationEngine(
            threshold=ENGINE_CONFIG["correlation_threshold"],
            window=ENGINE_CONFIG["correlation_lookback_bars"]
        )

        self.telegram_token = os.getenv("TELEGRAM_TOKEN")
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")

        self.telegram_controller = TelegramController(
            self.telegram_token,
            self.telegram_chat_id
        )

        chains = list(executors.keys())

        self.capital = CapitalAccounting(
            initial_equity=initial_equity,
            chains=chains
        )

        self.feeds: Dict[str, BinanceCandleFeed] = {}

        for s in self.symbols:
            logger.info(f"[FEED] Creating feed for {s}")
            self.feeds[s] = BinanceCandleFeed(s, interval)

        self.cooldown: Dict[str, float] = {}
        self.cooldown_seconds = ENGINE_CONFIG.get(
            "trade_cooldown_sec",
            ENGINE_CONFIG.get("trade_cooldown", 600)
        )

        self._liq_cache: Dict[str, Tuple[float, bool]] = {}
        self._liq_ttl_sec = ENGINE_CONFIG.get("liquidity_ttl_sec", 300)

        self._exec_timeout_sec = ENGINE_CONFIG.get("executor_timeout_sec", 12)
        self._exec_retries = ENGINE_CONFIG.get("executor_retries", 2)

        # key format: "{chain}:{symbol}" -> trade_id
        self.trade_ids: Dict[str, int] = {}

        self.equity_peak = initial_equity
        self.circuit_breaker_triggered = False
        self.circuit_breaker_time = None

        self._global_risk_reset_day: Optional[str] = None

        self._restore_open_trade_state()

    # ------------------------------------------------
    # INTERNAL HELPERS
    # ------------------------------------------------

    @staticmethod
    def _trade_key(chain: str, symbol: str) -> str:
        return f"{chain}:{symbol}"

    @staticmethod
    def _opposite_direction(direction: str) -> str:
        direction = str(direction).upper()
        if direction == "LONG":
            return "SHORT"
        if direction == "SHORT":
            return "LONG"
        return direction

    @staticmethod
    def _safe_float(value, default: float) -> float:
        try:
            if value is None:
                return float(default)
            return float(value)
        except Exception:
            return float(default)

    def _extract_success(self, result) -> bool:
        if result is None:
            return False
        return bool(getattr(result, "success", False))

    def _extract_executed_size(self, result, fallback_size: float) -> float:
        if result is None:
            return float(fallback_size)

        for attr in ("executed_size", "filled_size", "size"):
            if hasattr(result, attr):
                try:
                    value = getattr(result, attr)
                    if value is not None:
                        return float(value)
                except Exception:
                    pass

        if isinstance(result, dict):
            for key in ("executed_size", "filled_size", "size"):
                try:
                    value = result.get(key)
                    if value is not None:
                        return float(value)
                except Exception:
                    pass

        return float(fallback_size)

    def _get_open_chains_for_symbol(self, symbol: str) -> List[str]:
        chains = []
        for chain in self.executors.keys():
            if self.capital.has_position(chain, symbol):
                chains.append(chain)
        return chains

    def _has_any_chain_position(self, symbol: str) -> bool:
        return any(self.capital.has_position(chain, symbol) for chain in self.executors.keys())

    def _sync_global_risk_daily_baseline_if_needed(self) -> None:
        today = datetime.utcnow().date().isoformat()
        if self._global_risk_reset_day == today:
            return

        self.global_risk.reset_daily_baseline(self.capital.equity)
        self._global_risk_reset_day = today

    def _restore_open_trade_state(self) -> None:
        """
        Restores:
        - trade_ids per (chain, symbol)
        - symbol-level logical positions in PositionManager from open DB rows
        """
        try:
            rows = self.trade_logger.get_open_trades()
        except Exception as e:
            logger.error(f"[RECOVERY] failed to read open trades: {e}")
            return

        grouped: Dict[str, Dict[str, Any]] = {}

        for row in rows:
            try:
                trade_id, symbol, chain, direction, size, entry_price, atr, ts_open = row
            except Exception:
                continue

            self.trade_ids[self._trade_key(chain, symbol)] = int(trade_id)

            bucket = grouped.setdefault(symbol, {
                "direction": direction,
                "entry_price": float(entry_price),
                "atr": float(atr or 0.0),
                "size": 0.0,
                "entry_ts": int(ts_open),
            })

            bucket["size"] += float(size)

        for symbol, data in grouped.items():
            if self.position_manager.has_open_position(symbol):
                continue

            try:
                self.position_manager.open_position(
                    symbol=symbol,
                    direction=str(data["direction"]).upper(),
                    entry_price=float(data["entry_price"]),
                    size=float(data["size"]),
                    atr=max(float(data["atr"]), 1e-9),
                    entry_ts=int(data["entry_ts"]),
                )
                logger.info(f"[RECOVERY] restored in-memory position for {symbol}")
            except Exception as e:
                logger.error(f"[RECOVERY] failed to restore position for {symbol}: {e}")

    def send_telegram(self, message):

        if not self.telegram_token:
            return

        try:
            if hasattr(self.telegram_controller, "send_message"):
                self.telegram_controller.send_message(message)
                return

            if hasattr(self.telegram_controller, "send"):
                self.telegram_controller.send(message)
                return

            if hasattr(self.telegram_controller, "notify"):
                self.telegram_controller.notify(message)
                return
        except Exception as e:
            logger.error(f"Telegram controller error: {e}")

        try:
            url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"

            requests.post(
                url,
                json={"chat_id": self.telegram_chat_id, "text": message},
                timeout=5
            )

        except Exception as e:
            logger.error(f"Telegram error: {e}")

    def check_portfolio_drawdown(self):

        equity = self.capital.equity

        if equity > self.equity_peak:
            self.equity_peak = equity

        if self.equity_peak <= 0:
            return

        drawdown = (self.equity_peak - equity) / self.equity_peak

        limit = ENGINE_CONFIG.get("portfolio_circuit_breaker_dd", 0.10)

        if drawdown >= limit and not self.circuit_breaker_triggered:

            logger.critical(f"[CIRCUIT BREAKER] Portfolio DD {drawdown:.2%}")

            self.circuit_breaker_triggered = True
            self.circuit_breaker_time = time.time()

            self.send_telegram(f"🚨 Circuit breaker triggered {drawdown:.2%}")

    def _reset_circuit_breaker_if_needed(self):

        if not self.circuit_breaker_triggered:
            return

        cooldown = ENGINE_CONFIG.get("circuit_breaker_cooldown_minutes", 240) * 60

        if self.circuit_breaker_time and time.time() - self.circuit_breaker_time > cooldown:

            logger.info("[CIRCUIT BREAKER RESET] Trading resumed")

            self.circuit_breaker_triggered = False
            self.circuit_breaker_time = None
            self.equity_peak = self.capital.equity

    def _is_liquid(self, symbol):

        now = time.time()

        cached = self._liq_cache.get(symbol)

        if cached and (now - cached[0]) < self._liq_ttl_sec:
            return cached[1]

        allowed = True

        if LiquidityFilter:
            try:
                if hasattr(LiquidityFilter, "is_liquid"):
                    allowed = LiquidityFilter.is_liquid(symbol)
                elif hasattr(LiquidityFilter, "allow"):
                    allowed = LiquidityFilter.allow(symbol)
            except Exception:
                allowed = True

        if not allowed:
            logger.debug(f"[LIQUIDITY BLOCK] {symbol}")

        self._liq_cache[symbol] = (now, allowed)

        return allowed

    async def fetch_candle(self, symbol, feed):

        async with self.feed_semaphore:
            try:
                candle = await feed.get_latest_closed_candle()
                return symbol, candle

            except Exception as e:
                logger.error(f"[FEED ERROR] {symbol}: {e}")
                return symbol, None

    async def _with_retry(self, coro_factory, label):

        for attempt in range(self._exec_retries + 1):
            try:
                return await asyncio.wait_for(
                    coro_factory(),
                    timeout=self._exec_timeout_sec
                )

            except Exception as e:
                logger.warning(f"[EXECUTOR] {label} attempt {attempt + 1} failed: {e}")
                await asyncio.sleep(0.5)

        logger.error(f"[EXECUTOR] {label} failed")
        return None

    async def _process_exits(self, candle_map: Dict[str, Any], latest_prices: Dict[str, float]) -> None:
        open_symbols = list(self.position_manager.open_symbols())

        for symbol in open_symbols:
            candle = candle_map.get(symbol)
            if not candle:
                continue

            try:
                exit_decision = self.position_manager.check_exit(
                    symbol=symbol,
                    high=float(candle["high"]),
                    low=float(candle["low"]),
                )
            except Exception as e:
                logger.error(f"[EXIT CHECK ERROR] {symbol}: {e}")
                continue

            if not exit_decision:
                continue

            position = exit_decision["position"]
            exit_price = float(exit_decision["exit_price"])
            close_direction = self._opposite_direction(position.direction)

            routes = SYMBOL_ROUTES.get(symbol, {})
            open_chains = self._get_open_chains_for_symbol(symbol)

            if not open_chains:
                logger.warning(f"[EXIT] no accounting chains found for {symbol}; closing logical position only")
                self.position_manager.close_position(symbol)
                continue

            async def close_chain(chain: str):
                token = routes.get(chain)
                accounting_pos = self.capital.get_position(chain, symbol)

                if not token or accounting_pos is None:
                    return chain, None

                async def call():
                    executor = self.executors[chain]
                    return await executor.execute_trade(
                        symbol=token,
                        direction=close_direction,
                        size=float(accounting_pos.size),
                    )

                result = await self._with_retry(call, f"close {symbol} {chain}")
                return chain, result

            close_results = await asyncio.gather(*[
                close_chain(chain) for chain in open_chains
            ])

            successful_close_chains = []
            failed_close_chains = []

            for chain, result in close_results:
                if self._extract_success(result):
                    successful_close_chains.append(chain)
                else:
                    failed_close_chains.append(chain)

            if not successful_close_chains:
                logger.warning(f"[EXIT FAILED] {symbol} no close legs succeeded")
                continue

            for chain in successful_close_chains:
                trade_key = self._trade_key(chain, symbol)
                trade_id = self.trade_ids.get(trade_key)

                try:
                    pnl = self.capital.close_position(
                        chain=chain,
                        symbol=symbol,
                        exit_price=exit_price,
                    )
                except Exception as e:
                    logger.error(f"[CAPITAL CLOSE ERROR] {symbol} {chain}: {e}")
                    continue

                r_mult = self.position_manager.r_multiple(
                    entry_price=position.entry_price,
                    exit_price=exit_price,
                    stop_loss=position.stop_loss,
                    direction=position.direction,
                )

                if trade_id is not None:
                    try:
                        self.trade_logger.log_exit(
                            trade_id=trade_id,
                            exit_price=exit_price,
                            r_multiple=r_mult,
                            ts_close=int(time.time()),
                        )
                    except Exception as e:
                        logger.error(f"[TRADE EXIT LOGGER ERROR] {symbol} {chain}: {e}")
                else:
                    logger.warning(f"[TRADE ID MISSING] could not log exit for {chain}:{symbol}")

                self.trade_ids.pop(trade_key, None)

                logger.info(
                    f"[TRADE CLOSED] symbol={symbol} chain={chain} direction={position.direction} "
                    f"exit_price={exit_price} pnl={pnl:.6f} r={r_mult:.4f}"
                )

            if not self._has_any_chain_position(symbol):
                self.position_manager.close_position(symbol)
                self.cooldown[symbol] = time.time()

                self.send_telegram(
                    f"✅ Trade Closed {symbol} exit={exit_price} "
                    f"closed_chains={','.join(successful_close_chains)}"
                )
            else:
                logger.warning(
                    f"[PARTIAL EXIT] symbol={symbol} closed_chains={successful_close_chains} "
                    f"failed_chains={failed_close_chains}"
                )

            if latest_prices:
                try:
                    self.capital.mark_to_market(latest_prices)
                except Exception as e:
                    logger.error(f"[POST EXIT MTM ERROR] {symbol}: {e}")

    async def run(self):

        logger.info("Multi-chain engine started.")

        self._sync_global_risk_daily_baseline_if_needed()

        while True:

            self.capital.daily_reset_if_needed()
            self._sync_global_risk_daily_baseline_if_needed()

            self._reset_circuit_breaker_if_needed()

            candle_results = await asyncio.gather(*[
                self.fetch_candle(symbol, feed)
                for symbol, feed in self.feeds.items()
            ])

            latest_prices = {}
            newly_closed_symbols = set()
            candle_map: Dict[str, Any] = {}

            for symbol, candle in candle_results:

                if not candle:
                    continue

                close_time = candle["close_time"]

                if self.last_processed_candle.get(symbol) == close_time:
                    continue

                self.last_processed_candle[symbol] = close_time
                newly_closed_symbols.add(symbol)
                candle_map[symbol] = candle

                price = candle["close"]
                latest_prices[symbol] = price

                self.price_history.setdefault(symbol, []).append(price)

                if len(self.price_history[symbol]) > 100:
                    self.price_history[symbol].pop(0)

            if latest_prices:
                self.capital.mark_to_market(latest_prices)

            if candle_map:
                await self._process_exits(candle_map, latest_prices)

            self.check_portfolio_drawdown()

            if self.circuit_breaker_triggered:
                logger.warning("Circuit breaker active")
                await asyncio.sleep(self.loop_interval)
                continue

            now = time.time()

            if now - self.last_universe_refresh > self.universe_refresh_sec:

                self.active_universe = self.universe_selector.select(self.price_history) or self.symbols
                self.last_universe_refresh = now

                logger.info(f"[UNIVERSE REFRESH] {self.active_universe}")

            candidates = []

            for symbol, candle in candle_results:

                if not candle:
                    continue

                if symbol not in newly_closed_symbols:
                    continue

                if symbol not in self.active_universe:
                    continue

                if symbol in self.position_manager.open_symbols():
                    continue

                if not self.position_manager.can_open_new():
                    break

                if symbol in self.cooldown and time.time() - self.cooldown[symbol] < self.cooldown_seconds:
                    continue

                if not self._is_liquid(symbol):
                    continue

                price = candle["close"]

                out = self.routers[symbol].on_candle(
                    price,
                    candle["high"],
                    candle["low"],
                    candle["close_time"]
                )

                if out.signal:

                    self.trade_logger.log_signal(
                        symbol=symbol,
                        direction=out.signal.direction,
                        price=price,
                        atr=out.signal.atr
                    )

                    candidates.append({
                        "symbol": symbol,
                        "signal": out.signal,
                        "price": price
                    })

            if not candidates:
                await asyncio.sleep(self.loop_interval)
                continue

            best = rank_signals(
                candidates,
                correlation_engine=self.correlation,
                open_symbols=self.position_manager.open_symbols()
            )

            if not best:
                await asyncio.sleep(self.loop_interval)
                continue

            symbol = best.symbol
            direction = best.signal.direction
            atr = best.signal.atr

            price = next(
                (c["price"] for c in candidates if c["symbol"] == symbol),
                None
            )

            if price is None:
                logger.warning(f"[PRICE MISSING] could not resolve candidate price for {symbol}")
                await asyncio.sleep(self.loop_interval)
                continue

            base_size = self.risk.calculate_position_size(
                self.capital.equity,
                price,
                atr
            )

            base_size *= self.vol_scaler.scale(self.price_history.get(symbol, []))
            base_size *= self.signal_strength.scale(best.signal)

            decision = self.global_risk.approve_trade(
                equity=self.capital.equity,
                proposed_notional=base_size * price
            )

            if not decision.allowed:
                logger.warning(f"[GLOBAL RISK BLOCK] {decision.reason}")
                await asyncio.sleep(self.loop_interval)
                continue

            routes = SYMBOL_ROUTES.get(symbol, {})

            executable_chains = [
                chain for chain in self.executors
                if routes.get(chain)
            ]

            if not executable_chains:
                logger.warning(f"[NO EXECUTION ROUTE] {symbol}")
                await asyncio.sleep(self.loop_interval)
                continue

            chain_size = base_size / len(executable_chains)

            async def execute_chain(chain):

                token = routes.get(chain)

                async def call():

                    executor = self.executors[chain]

                    return await executor.execute_trade(
                        symbol=token,
                        direction=direction,
                        size=chain_size
                    )

                return await self._with_retry(call, f"open {symbol} {chain}")

            execution_results = await asyncio.gather(*[
                execute_chain(c) for c in executable_chains
            ])

            successful_legs = []
            failed_chains = []

            for chain, result in zip(executable_chains, execution_results):
                if self._extract_success(result):
                    leg_size = self._extract_executed_size(result, chain_size)
                    successful_legs.append((chain, result, leg_size))
                else:
                    failed_chains.append(chain)

            if successful_legs:

                entry_ts = int(time.time())
                total_executed_size = sum(leg_size for _, _, leg_size in successful_legs)

                for chain, result, executed_chain_size in successful_legs:
                    trade_id = None

                    try:
                        trade_id = self.trade_logger.log_entry(
                            symbol=symbol,
                            chain=chain,
                            direction=direction,
                            size=executed_chain_size,
                            entry_price=price,
                            atr=atr,
                            ts_open=entry_ts
                        )
                    except Exception as e:
                        logger.error(
                            f"[TRADE LOGGER ERROR] failed to persist entry for {symbol} on {chain}: {e}"
                        )

                    if trade_id is not None:
                        self.trade_ids[self._trade_key(chain, symbol)] = trade_id

                    try:
                        self.capital.open_position(
                            chain=chain,
                            symbol=symbol,
                            direction=direction,
                            entry_price=price,
                            size=executed_chain_size
                        )
                    except Exception as e:
                        logger.error(
                            f"[CAPITAL ERROR] failed to open accounting position for {symbol} on {chain}: {e}"
                        )

                self.global_risk.on_trade_executed()

                self.cooldown[symbol] = time.time()

                self.position_manager.open_position(
                    symbol=symbol,
                    direction=direction,
                    entry_price=price,
                    size=total_executed_size,
                    atr=atr,
                    entry_ts=entry_ts
                )

                logger.info(
                    f"[TRADE OPENED] symbol={symbol} direction={direction} "
                    f"price={price} size={total_executed_size} "
                    f"chains={[chain for chain, _, _ in successful_legs]} "
                    f"failed_chains={failed_chains}"
                )

                self.send_telegram(
                    f"🚀 Trade Opened {symbol} {direction} size={total_executed_size} "
                    f"chains={','.join(chain for chain, _, _ in successful_legs)}"
                )

            await asyncio.sleep(self.loop_interval)