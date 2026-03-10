import asyncio
import json
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

        self.strategy_state_path = os.getenv("STRATEGY_STATE_PATH", "strategy_state.json")

        # entry diagnostics
        self._entry_debug_enabled = True
        self._entry_skip_reasons: Dict[str, int] = {}

        # strategy diagnostics
        self._strategy_debug_enabled = True
        self._strategy_debug_log_signals = True

        self._last_health_log_time = 0.0
        self._health_log_interval_sec = 300

        self._restore_open_trade_state()
        self._load_strategy_state()

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

    def _extract_tx_hash(self, result):
        if result is None:
            return None

        for attr in ("tx_hash", "transaction_hash", "hash"):
            if hasattr(result, attr):
                value = getattr(result, attr)
                if value:
                    return str(value)

        if isinstance(result, dict):
            for key in ("tx_hash", "transaction_hash", "hash"):
                value = result.get(key)
                if value:
                    return str(value)

        return None

    def _extract_status(self, result):
        if result is None:
            return None

        for attr in ("status", "fill_status", "state"):
            if hasattr(result, attr):
                value = getattr(result, attr)
                if value is not None:
                    return str(value)

        if isinstance(result, dict):
            for key in ("status", "fill_status", "state"):
                value = result.get(key)
                if value is not None:
                    return str(value)

        return None

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

    def _save_strategy_state(self) -> None:
        try:
            data = {
                "saved_at": int(time.time()),
                "last_processed_candle": self.last_processed_candle,
                "cooldown": self.cooldown,
                "routers": {},
            }

            for symbol, router in self.routers.items():
                if hasattr(router, "to_snapshot"):
                    data["routers"][symbol] = router.to_snapshot()

            tmp_path = f"{self.strategy_state_path}.tmp"

            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f)

            os.replace(tmp_path, self.strategy_state_path)

            logger.info(
                f"[STATE SAVE] saved strategy state for {len(data['routers'])} symbols "
                f"to {self.strategy_state_path}"
            )

        except Exception as e:
            logger.error(f"[STATE SAVE ERROR] {e}")

    def _load_strategy_state(self) -> None:
        if not os.path.exists(self.strategy_state_path):
            logger.info(f"[STATE LOAD] no strategy state file at {self.strategy_state_path}")
            return

        try:
            with open(self.strategy_state_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.last_processed_candle = data.get("last_processed_candle", {}) or {}
            self.cooldown = data.get("cooldown", {}) or {}

            router_snaps = data.get("routers", {}) or {}
            restored = 0

            for symbol, snap in router_snaps.items():
                router = self.routers.get(symbol)
                if router and hasattr(router, "from_snapshot"):
                    router.from_snapshot(snap)
                    restored += 1

            logger.info(f"[STATE LOAD] restored strategy state for {restored} symbols")

        except Exception as e:
            logger.error(f"[STATE LOAD ERROR] {e}")

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

    def _log_exit_state(
        self,
        symbol: str,
        candle: Dict[str, Any],
        pre_snapshot: Optional[Dict[str, Any]],
        exit_decision: Optional[Dict[str, Any]],
        open_chains: List[str],
    ) -> None:

        if not pre_snapshot:
            return

        high = self._safe_float(candle.get("high"), 0.0)
        low = self._safe_float(candle.get("low"), 0.0)
        close = self._safe_float(candle.get("close"), 0.0)

        if exit_decision and isinstance(exit_decision, dict):
            diag = exit_decision.get("diagnostic", {})
            logger.info(
                "[EXIT CHECK] "
                f"symbol={symbol} "
                f"direction={pre_snapshot.get('direction')} "
                f"entry={pre_snapshot.get('entry_price')} "
                f"atr={pre_snapshot.get('atr')} "
                f"best_pre={diag.get('pre_best_price', pre_snapshot.get('best_price'))} "
                f"best_post={diag.get('post_best_price', pre_snapshot.get('best_price'))} "
                f"stop_pre={diag.get('pre_stop_loss', pre_snapshot.get('stop_loss'))} "
                f"stop_post={diag.get('post_stop_loss', pre_snapshot.get('stop_loss'))} "
                f"high={high} low={low} close={close} "
                f"chains={open_chains} "
                f"triggered=True result={exit_decision.get('result')} "
                f"exit_price={exit_decision.get('exit_price')}"
            )
        else:
            logger.info(
                "[EXIT CHECK] "
                f"symbol={symbol} "
                f"direction={pre_snapshot.get('direction')} "
                f"entry={pre_snapshot.get('entry_price')} "
                f"atr={pre_snapshot.get('atr')} "
                f"best={pre_snapshot.get('best_price')} "
                f"stop={pre_snapshot.get('stop_loss')} "
                f"high={high} low={low} close={close} "
                f"chains={open_chains} "
                f"triggered=False"
            )

    def _log_entry_skip(self, symbol: str, reason: str, extra: Optional[str] = None) -> None:
        if reason != "not_newly_closed":
            self._entry_skip_reasons[reason] = self._entry_skip_reasons.get(reason, 0) + 1

        if not self._entry_debug_enabled:
            return

        if reason == "not_newly_closed":
            return

        if extra:
            logger.info(f"[ENTRY SKIP] symbol={symbol} reason={reason} {extra}")
        else:
            logger.info(f"[ENTRY SKIP] symbol={symbol} reason={reason}")

    def _flush_entry_skip_summary(self) -> None:
        if not self._entry_skip_reasons:
            return

        summary = ", ".join(
            f"{reason}={count}" for reason, count in sorted(self._entry_skip_reasons.items())
        )
        logger.info(f"[ENTRY SUMMARY] {summary}")
        self._entry_skip_reasons = {}

    def _compact_meta(self, meta: Any) -> str:
        if not isinstance(meta, dict) or not meta:
            return ""

        preferred_keys = [
            "close",
            "price",
            "high",
            "low",
            "atr",
            "atr_percentile",
            "zscore",
            "mean",
            "std",
            "close_history_len",
            "atr_history_len",
            "bb_period",
            "atr_period",
            "z_entry",
            "max_atr_percentile_for_mr",
            "slope_norm",
            "slope_threshold",
            "vol_percentile",
            "vol_threshold",
            "breakout_high",
            "breakout_low",
            "breakout_distance",
            "previous_slope",
        ]

        parts = []

        for key in preferred_keys:
            if key not in meta:
                continue

            value = meta.get(key)

            if isinstance(value, float):
                parts.append(f"{key}={value:.6f}")
            else:
                parts.append(f"{key}={value}")

        if not parts:
            try:
                for key, value in list(meta.items())[:8]:
                    if isinstance(value, float):
                        parts.append(f"{key}={value:.6f}")
                    else:
                        parts.append(f"{key}={value}")
            except Exception:
                return ""

        return " ".join(parts)

    def _log_strategy_result(self, symbol: str, out: Any) -> None:
        if not self._strategy_debug_enabled:
            return

        signal = getattr(out, "signal", None)
        regime = getattr(out, "regime", None)
        strategy_used = getattr(out, "strategy_used", None)
        reason = getattr(out, "reason", None)
        meta = getattr(out, "meta", None)

        if regime is None and isinstance(out, dict):
            regime = out.get("regime")
        if strategy_used is None and isinstance(out, dict):
            strategy_used = out.get("strategy_used")
        if reason is None and isinstance(out, dict):
            reason = out.get("reason")
        if meta is None and isinstance(out, dict):
            meta = out.get("meta")
        if signal is None and isinstance(out, dict):
            signal = out.get("signal")

        regime = regime or "UNKNOWN"
        strategy_used = strategy_used or "unknown"

        meta_str = self._compact_meta(meta)
        meta_suffix = f" {meta_str}" if meta_str else ""

        if signal is None:
            logger.info(
                f"[STRATEGY CHECK] symbol={symbol} regime={regime} "
                f"strategy={strategy_used} result=no_signal reason={reason or 'unknown'}{meta_suffix}"
            )
            return

        if not self._strategy_debug_log_signals:
            return

        direction = getattr(signal, "direction", None)
        atr = getattr(signal, "atr", None)

        atr_part = ""
        if atr is not None:
            try:
                atr_part = f" atr={float(atr):.6f}"
            except Exception:
                atr_part = f" atr={atr}"

        logger.info(
            f"[STRATEGY CHECK] symbol={symbol} regime={regime} "
            f"strategy={strategy_used} result=signal direction={direction}{atr_part}{meta_suffix}"
        )

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

            pre_snapshot = self.position_manager.diagnostic_snapshot(symbol)
            open_chains = self._get_open_chains_for_symbol(symbol)

            try:
                exit_decision = self.position_manager.check_exit(
                    symbol=symbol,
                    high=float(candle["high"]),
                    low=float(candle["low"]),
                )
            except Exception as e:
                logger.error(f"[EXIT CHECK ERROR] {symbol}: {e}")
                continue

            self._log_exit_state(
                symbol=symbol,
                candle=candle,
                pre_snapshot=pre_snapshot,
                exit_decision=exit_decision,
                open_chains=open_chains,
            )

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

        try:
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
                    self._save_strategy_state()

                self.check_portfolio_drawdown()

                now = time.time()

                if now - self._last_health_log_time >= self._health_log_interval_sec:
                    logger.info(
                        f"[HEALTH] equity={self.capital.equity:.6f} "
                        f"open_positions={len(self.position_manager.open_symbols())} "
                        f"breaker={self.circuit_breaker_triggered} "
                        f"symbols={len(self.symbols)} "
                        f"newly_closed={len(newly_closed_symbols)}"
                    )
                    self._last_health_log_time = now

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
                self._entry_skip_reasons = {}

                for symbol, candle in candle_results:

                    if not candle:
                        self._log_entry_skip(symbol, "no_candle")
                        continue

                    if symbol not in newly_closed_symbols:
                        self._log_entry_skip(symbol, "not_newly_closed")
                        continue

                    if symbol not in self.active_universe:
                        self._log_entry_skip(symbol, "not_in_active_universe")
                        continue

                    if symbol in self.position_manager.open_symbols():
                        self._log_entry_skip(symbol, "already_open")
                        continue

                    if not self.position_manager.can_open_new():
                        self._log_entry_skip(symbol, "max_positions_reached")
                        break

                    if symbol in self.cooldown and time.time() - self.cooldown[symbol] < self.cooldown_seconds:
                        remaining = self.cooldown_seconds - (time.time() - self.cooldown[symbol])
                        self._log_entry_skip(symbol, "cooldown", f"remaining_sec={remaining:.2f}")
                        continue

                    if not self._is_liquid(symbol):
                        self._log_entry_skip(symbol, "liquidity_block")
                        continue

                    price = candle["close"]

                    out = self.routers[symbol].on_candle(
                        price,
                        candle["high"],
                        candle["low"],
                        candle["close_time"]
                    )

                    self._log_strategy_result(symbol, out)

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
                            "price": price,
                            "meta": getattr(out, "meta", {}) or {},
                            "regime": getattr(out, "regime", None),
                            "strategy_used": getattr(out, "strategy_used", None),
                        })
                    else:
                        self._log_entry_skip(symbol, "no_signal")

                if not candidates:
                    self._flush_entry_skip_summary()
                    logger.info("[SCAN] no candidates produced this loop")
                    await asyncio.sleep(self.loop_interval)
                    continue

                best = rank_signals(
                    candidates,
                    correlation_engine=self.correlation,
                    open_symbols=self.position_manager.open_symbols()
                )

                if not best:
                    self._flush_entry_skip_summary()
                    logger.info(f"[SCAN] candidates={len(candidates)} but ranker returned no selection")
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

                best_meta = next(
                    (c.get("meta", {}) for c in candidates if c["symbol"] == symbol),
                    {}
                )

                base_size *= self.signal_strength.scale(best.signal, best_meta)

                max_trade_fraction = GLOBAL_RISK_CONFIG["max_trade_fraction"]
                max_notional = self.capital.equity * max_trade_fraction

                if price > 0:
                    capped_size = min(base_size, max_notional / price)
                else:
                    capped_size = 0.0

                if capped_size < base_size:
                    logger.info(
                        f"[SIZE CLAMP] symbol={symbol} "
                        f"base_size={base_size:.6f} capped_size={capped_size:.6f} "
                        f"price={price:.6f} max_notional={max_notional:.6f}"
                    )

                base_size = capped_size

                logger.info(
                    f"[RISK CHECK] symbol={symbol} equity={self.capital.equity:.6f} "
                    f"price={price:.6f} atr={float(atr):.6f} base_size={base_size:.6f} "
                    f"proposed_notional={(base_size * price):.6f}"
                )

                decision = self.global_risk.approve_trade(
                    equity=self.capital.equity,
                    proposed_notional=base_size * price
                )

            

                if not decision.allowed:
                    self._flush_entry_skip_summary()
                    logger.warning(f"[GLOBAL RISK BLOCK] {decision.reason}")
                    await asyncio.sleep(self.loop_interval)
                    continue

                routes = SYMBOL_ROUTES.get(symbol, {})

                executable_chains = [
                    chain for chain in self.executors
                    if routes.get(chain)
                ]

                if not executable_chains:
                    self._flush_entry_skip_summary()
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

                        tx_hash = self._extract_tx_hash(result)
                        status = self._extract_status(result)

                        logger.info(
                            f"[EXECUTION OK] symbol={symbol} chain={chain} direction={direction} "
                            f"requested_size={chain_size} executed_size={executed_chain_size} "
                            f"tx_hash={tx_hash} status={status}"
                        )

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

                    self._flush_entry_skip_summary()

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
                else:
                    self._flush_entry_skip_summary()
                    logger.warning(
                        f"[EXECUTION FAILED] symbol={symbol} direction={direction} "
                        f"chains={executable_chains} failed_chains={failed_chains}"
                    )

                await asyncio.sleep(self.loop_interval)

        finally:
            self._save_strategy_state()