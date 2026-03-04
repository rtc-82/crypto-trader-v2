from typing import Dict, Any, Optional

from engine.execution.interfaces import (
    LiveExecutorInterface,
    ExecutionResult,
)

from engine.execution.base.base_live_executor import BaseLiveExecutor


class BaseExecutor(LiveExecutorInterface):
    """
    Adapter layer between MultiChainOrchestrator
    and BaseLiveExecutor.

    This class does NOT build transactions itself.
    It delegates to BaseLiveExecutor.
    """

    def __init__(
        self,
        live_executor: BaseLiveExecutor,
        mode: str = "paper",
    ):
        self.live = live_executor
        self.mode = mode  # "paper" or "live"

    # ==========================================================
    # HEALTH CHECK
    # ==========================================================

    async def health_check(self) -> bool:

        try:

            if self.mode == "paper":
                return True

            balance = self.live.provider.get_balance_eth()

            return balance is not None

        except Exception:

            return False

    # ==========================================================
    # BALANCE
    # ==========================================================

    async def get_balance(self) -> float:

        if self.mode == "paper":

            return 100.0

        return float(self.live.provider.get_balance_eth())

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
    # EXECUTION
    # ==========================================================

    async def execute_long(
        self,
        symbol: str,
        size: float,
        metadata: Dict[str, Any],
    ) -> ExecutionResult:
        """
        LONG = WETH -> USDC
        size expected in ETH units
        """

        if self.mode == "paper":

            return ExecutionResult(
                success=True,
                tx_id="paper_tx",
                filled_size=size,
                average_price=None,
                raw_response=None,
            )

        try:

            result = self.live.execute_weth_to_usdc(
                weth_amount_eth=size,
                wrap_eth_first=True,
                max_approve=True,
            )

            return ExecutionResult(
                success=True,
                tx_id=result.get("swap"),
                filled_size=size,
                average_price=None,
                raw_response=result,
            )

        except Exception as e:

            return ExecutionResult(
                success=False,
                tx_id=None,
                filled_size=0.0,
                average_price=None,
                raw_response={"error": str(e)},
            )

    async def execute_short(
        self,
        symbol: str,
        size: float,
        metadata: Dict[str, Any],
    ) -> ExecutionResult:
        """
        SHORT = USDC -> WETH
        """

        return await self.execute_long(symbol, size, metadata)

    async def close_position(
        self,
        symbol: str,
    ) -> ExecutionResult:

        if self.mode == "paper":

            return ExecutionResult(
                success=True,
                tx_id="paper_close",
                filled_size=0.0,
                average_price=None,
                raw_response=None,
            )

        try:

            result = self.live.execute_weth_to_usdc(
                weth_amount_eth=0.0,
                wrap_eth_first=False,
                max_approve=True,
            )

            return ExecutionResult(
                success=True,
                tx_id=result.get("swap"),
                filled_size=0.0,
                average_price=None,
                raw_response=result,
            )

        except Exception as e:

            return ExecutionResult(
                success=False,
                tx_id=None,
                filled_size=0.0,
                average_price=None,
                raw_response={"error": str(e)},
            )