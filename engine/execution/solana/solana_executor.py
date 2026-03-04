from __future__ import annotations

from typing import Any, Dict, Optional

from engine.execution.interfaces import LiveExecutorInterface, ExecutionResult
from engine.execution.solana.solana_wallet import SolanaWallet
from engine.execution.solana.jupiter_execution_engine import JupiterExecutionEngine


class SolanaExecutor(LiveExecutorInterface):
    """
    Solana execution adapter.

    LONG  = SOL -> USDC
    SHORT = USDC -> SOL
    """

    def __init__(
        self,
        wallet: SolanaWallet,
        jupiter: JupiterExecutionEngine,
        mode: str = "paper",
    ):
        self.wallet = wallet
        self.jupiter = jupiter
        self.mode = mode

    # ==========================================================
    # HEALTH CHECK
    # ==========================================================

    async def health_check(self) -> bool:

        try:

            if self.mode == "paper":

                return True

            bal = await self.wallet.get_sol_balance()

            return bal is not None

        except Exception:

            return False

    # ==========================================================
    # BALANCE
    # ==========================================================

    async def get_balance(self) -> float:

        if self.mode == "paper":

            return 100.0

        return await self.wallet.get_sol_balance()

    # ==========================================================
    # GENERIC EXECUTION (used by orchestrator)
    # ==========================================================

    async def execute_trade(
        self,
        symbol: str,
        direction: str,
        size: float,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ExecutionResult:

        metadata = metadata or {}

        if direction == "LONG":

            return await self.execute_long(symbol, size, metadata)

        if direction == "SHORT":

            return await self.execute_short(symbol, size, metadata)

        raise ValueError(f"Invalid direction: {direction}")

    # ==========================================================
    # LONG
    # ==========================================================

    async def execute_long(
        self,
        symbol: str,
        size: float,
        metadata: Dict[str, Any],
    ) -> ExecutionResult:

        if self.mode == "paper":

            return ExecutionResult(True, "paper_tx", size, None, {"paper": True})

        try:

            tx = await self.jupiter.swap_sol_to_usdc(sol_amount=size)

            return ExecutionResult(
                True,
                tx.get("tx_id"),
                size,
                tx.get("avg_price"),
                tx
            )

        except Exception as e:

            return ExecutionResult(
                False,
                None,
                0.0,
                None,
                {"error": str(e)}
            )

    # ==========================================================
    # SHORT
    # ==========================================================

    async def execute_short(
        self,
        symbol: str,
        size: float,
        metadata: Dict[str, Any],
    ) -> ExecutionResult:

        if self.mode == "paper":

            return ExecutionResult(True, "paper_tx", size, None, {"paper": True})

        try:

            tx = await self.jupiter.swap_usdc_to_sol(usdc_amount=size)

            return ExecutionResult(
                True,
                tx.get("tx_id"),
                size,
                tx.get("avg_price"),
                tx
            )

        except Exception as e:

            return ExecutionResult(
                False,
                None,
                0.0,
                None,
                {"error": str(e)}
            )

    # ==========================================================
    # CLOSE
    # ==========================================================

    async def close_position(self, symbol: str) -> ExecutionResult:

        return ExecutionResult(
            True,
            "close_noop",
            0.0,
            None,
            {"close": "noop"}
        )