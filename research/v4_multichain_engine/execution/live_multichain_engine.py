from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from research.v4_multichain_engine.strategy_engine import StrategyEngine
from research.v4_multichain_engine.risk.global_risk_engine import GlobalRiskEngine
from research.v4_multichain_engine.wallet.solana_wallet import SolanaWallet
from research.v4_multichain_engine.execution.abstract_executor import AbstractExecutor
from research.v4_multichain_engine.execution.binance_candle_feed import BinanceCandleFeed
from research.v4_multichain_engine.utils.logger import setup_logger


logger = setup_logger()


# ==========================================================
# CONFIG
# ==========================================================

@dataclass
class LiveEngineConfig:
    mode: str = "paper"
    loop_interval_sec: float = 10.0

    trading_enabled: bool = False
    kill_switch_path: str = "KILL_SWITCH"
    min_sol_reserve: float = 0.05
    max_consecutive_errors: int = 5

    max_daily_loss: float = 5.0
    max_trade_fraction: float = 0.10
    max_trades_per_hour: int = 6

    default_trade_lamports: int = 10_000_000


# ==========================================================
# ENGINE
# ==========================================================

class LiveMultiChainEngine:

    def __init__(
        self,
        *,
        config: LiveEngineConfig,
        wallet: Optional[SolanaWallet],
        strategy: StrategyEngine,
        risk: GlobalRiskEngine,
        executor: AbstractExecutor,
        state_path: str = "engine_state_solana.json",
        notifier=None,
    ):
        self.cfg = config
        self.wallet = wallet
        self.strategy = strategy
        self.risk = risk
        self.executor = executor
        self.state_path = state_path
        self.notifier = notifier

        self.candle_feed = BinanceCandleFeed(symbol="SOLUSDT", interval="5m")

        self.state: Dict[str, Any] = {
            "engine_status": "RUNNING",
            "consecutive_errors": 0,
            "last_signal_hash": None,
            "last_tx_signature": None,
            "last_tick_ts": None,

            # 🔥 PnL Tracking
            "position": None,  # "LONG" | "SHORT"
            "entry_price": None,
            "position_size": None,
            "realized_pnl": 0.0,
            "daily_realized_pnl": 0.0,
            "last_reset_day": None,
        }

    # ==========================================================
    # PERSISTENCE
    # ==========================================================

    def _load_state(self):
        if os.path.exists(self.state_path):
            try:
                with open(self.state_path, "r") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    self.state.update(data)
                logger.info("State loaded successfully.")
            except Exception as e:
                logger.warning(f"Failed to load state file: {e}")

    def _save_state(self):
        try:
            tmp = self.state_path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(self.state, f, indent=2, default=str)
            os.replace(tmp, self.state_path)
        except Exception as e:
            logger.error(f"Failed to save state file: {e}")

    # ==========================================================
    # DAILY RESET
    # ==========================================================

    def _reset_daily_if_needed(self):
        today = time.strftime("%Y-%m-%d")

        if self.state["last_reset_day"] != today:
            self.state["daily_realized_pnl"] = 0.0
            self.state["last_reset_day"] = today
            logger.info("Daily PnL reset.")

    # ==========================================================
    # CONTROL
    # ==========================================================

    def _kill_switch_triggered(self):
        return os.path.exists(self.cfg.kill_switch_path)

    def _lock(self, reason: str):
        logger.critical(f"ENGINE LOCKED: {reason}")
        self.state["engine_status"] = "LOCKED"
        self.state["lock_reason"] = reason
        self._save_state()

        if self.notifier:
            asyncio.create_task(
                self.notifier.send_message(f"🚨 ENGINE LOCKED\nReason: {reason}")
            )

    # ==========================================================
    # INITIALIZATION
    # ==========================================================

    async def initialize(self) -> None:
        self._load_state()

        if self.cfg.mode == "live":
            if self.wallet is None:
                raise RuntimeError("Live mode requires wallet.")

            balance = await self.wallet.get_sol_balance()
            logger.info(f"Wallet SOL balance: {balance:.6f}")
        else:
            logger.info("Paper mode active.")

        logger.info("Engine initialized successfully.")

    # ==========================================================
    # MAIN LOOP
    # ==========================================================

    async def run_loop(self) -> None:
        logger.info("Engine main loop started.")

        while True:
            try:
                if self._kill_switch_triggered():
                    self._lock("Kill switch detected")
                    return

                await self._tick()
                self.state["consecutive_errors"] = 0

            except Exception as e:
                self.state["consecutive_errors"] += 1
                logger.exception(f"Engine error: {e}")

                if self.notifier:
                    asyncio.create_task(
                        self.notifier.send_message(
                            f"⚠ Engine Error\nCount: {self.state['consecutive_errors']}\n{e}"
                        )
                    )

                if self.state["consecutive_errors"] >= self.cfg.max_consecutive_errors:
                    self._lock("Too many consecutive errors")
                    return

            self.state["last_tick_ts"] = int(time.time())
            self._save_state()
            await asyncio.sleep(self.cfg.loop_interval_sec)

    # ==========================================================
    # TICK
    # ==========================================================

    async def _tick(self):

        if self.state["engine_status"] == "LOCKED":
            return

        if not self.cfg.trading_enabled:
            return

        self._reset_daily_if_needed()

        candle = await self.candle_feed.get_latest_closed_candle()
        if candle is None:
            return

        current_price = candle["close"]
        logger.info(f"Candle {candle['timestamp']} Close={current_price}")

        signal = self.strategy.generate_signal(
            price=current_price,
            high=candle["high"],
            low=candle["low"],
            timestamp=candle["timestamp"],
        )

        if signal is None:
            return

        new_direction = signal.direction  # "LONG" or "SHORT"
        current_position = self.state["position"]

        # --------------------------------------------------
        # Close existing position if opposite
        # --------------------------------------------------
        if current_position and current_position != new_direction:

            entry_price = self.state["entry_price"]
            size = self.state["position_size"]

            if current_position == "LONG":
                pnl = (current_price - entry_price) * size
            else:
                pnl = (entry_price - current_price) * size

            self.state["realized_pnl"] += pnl
            self.state["daily_realized_pnl"] += pnl

            logger.info(f"Position closed. PnL: {pnl:.4f}")

            if self.notifier:
                asyncio.create_task(
                    self.notifier.send_message(
                        f"🔄 Position Closed\nPnL: {pnl:.4f}\nDaily: {self.state['daily_realized_pnl']:.4f}"
                    )
                )

            self.state["position"] = None
            self.state["entry_price"] = None
            self.state["position_size"] = None

        # --------------------------------------------------
        # Open new position if none
        # --------------------------------------------------
        if self.state["position"] is None:

            trade_amount = self.cfg.default_trade_lamports
            size = trade_amount / current_price

            self.state["position"] = new_direction
            self.state["entry_price"] = current_price
            self.state["position_size"] = size

            logger.info(f"Opened {new_direction} at {current_price}")

            if self.notifier:
                asyncio.create_task(
                    self.notifier.send_message(
                        f"🚀 Opened {new_direction}\nPrice: {current_price}"
                    )
                )