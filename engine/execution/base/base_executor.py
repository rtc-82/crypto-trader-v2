from typing import Dict, Any, Optional

from engine.execution.interfaces import (
    LiveExecutorInterface,
    ExecutionResult,
)

from engine.execution.base.base_live_executor import BaseLiveExecutor


class BaseExecutor(LiveExecutorInterface):
    """
    Symbol-aware adapter between MultiChainOrchestrator and BaseLiveExecutor.

    Conventions:
    - symbol is expected to be the Base asset symbol from symbol_routes.py
      Example: "AAVE", "RENDER"
    - LONG  -> buy asset with configured quote token
    - SHORT -> sell asset into configured quote token

    Important:
    - SHORT on Base in this implementation is a SPOT SELL, not a true short borrow.
    """

    def __init__(
        self,
        live_executor: BaseLiveExecutor,
        mode: str = "paper",
    ):
        self.live = live_executor
        self.mode = mode

    async def health_check(self) -> bool:
        try:
            if self.mode == "paper":
                return True

            balance = self.live.provider.get_balance_eth()
            return balance is not None
        except Exception:
            return False

    async def get_balance(self) -> float:
        if self.mode == "paper":
            return 100.0

        return float(self.live.provider.get_balance_eth())

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

    async def execute_long(
        self,
        symbol: str,
        size: float,
        metadata: Dict[str, Any],
    ) -> ExecutionResult:
        """
        LONG = quote-token -> asset
        size = desired asset amount (human units)
        """
        if self.mode == "paper":
            return ExecutionResult(
                success=True,
                tx_id="paper_tx",
                filled_size=size,
                average_price=None,
                raw_response={
                    "mode": "paper",
                    "symbol": symbol,
                    "direction": "LONG",
                    "size": size,
                },
            )

        try:
            result = self.live.buy_token_with_quote(
                asset_symbol=symbol,
                desired_token_amount=size,
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
                raw_response={"error": str(e), "symbol": symbol, "direction": "LONG"},
            )

    async def execute_short(
        self,
        symbol: str,
        size: float,
        metadata: Dict[str, Any],
    ) -> ExecutionResult:
        """
        SHORT = asset -> quote-token SPOT SELL

        This is not a real borrow-based short.
        """
        if self.mode == "paper":
            return ExecutionResult(
                success=True,
                tx_id="paper_tx",
                filled_size=size,
                average_price=None,
                raw_response={
                    "mode": "paper",
                    "symbol": symbol,
                    "direction": "SHORT",
                    "size": size,
                },
            )

        try:
            result = self.live.sell_token_to_quote(
                asset_symbol=symbol,
                token_amount=size,
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
                raw_response={"error": str(e), "symbol": symbol, "direction": "SHORT"},
            )

    async def close_position(
        self,
        symbol: str,
    ) -> ExecutionResult:
        """
        Not used by your current orchestrator close path.
        """
        if self.mode == "paper":
            return ExecutionResult(
                success=True,
                tx_id="paper_close",
                filled_size=0.0,
                average_price=None,
                raw_response={"mode": "paper", "symbol": symbol},
            )

        return ExecutionResult(
            success=False,
            tx_id=None,
            filled_size=0.0,
            average_price=None,
            raw_response={
                "error": "close_position(symbol) is not used in current orchestrator flow",
                "symbol": symbol,
            },
        )