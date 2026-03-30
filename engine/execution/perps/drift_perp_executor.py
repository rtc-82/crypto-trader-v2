from __future__ import annotations

from typing import Dict, Any, Optional

from engine.execution.interfaces import (
    LiveExecutorInterface,
    ExecutionResult,
)


class DriftPerpExecutor(LiveExecutorInterface):
    """
    Solana perpetual futures executor placeholder for Drift.

    Paper mode:
        - Simulates successful perp entries/exits
        - Supports LONG and SHORT

    Live mode:
        - Not wired yet
        - Safe failure until real Drift SDK integration is added
    """

    def __init__(
        self,
        mode: str = "paper",
        logger=None,
    ):
        self.mode = (mode or "paper").strip().lower()
        self.logger = logger

    async def health_check(self) -> bool:
        return True

    async def get_balance(self) -> float:
        return 100.0

    async def execute_trade(
        self,
        symbol: str,
        direction: str,
        size: float,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ExecutionResult:
        metadata = metadata or {}
        direction = str(direction).upper()

        if direction == "LONG":
            return await self.execute_long(symbol, size, metadata)

        if direction == "SHORT":
            return await self.execute_short(symbol, size, metadata)

        return ExecutionResult(
            success=False,
            tx_id=None,
            filled_size=0.0,
            average_price=None,
            raw_response={"error": f"Invalid direction: {direction}"},
        )

    async def execute_long(
        self,
        symbol: str,
        size: float,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ExecutionResult:
        metadata = metadata or {}

        if self.mode == "paper":
            if self.logger:
                self.logger.info(
                    "[DRIFT PERP][PAPER] open LONG symbol=%s size=%s metadata=%s",
                    symbol,
                    size,
                    metadata,
                )

            return ExecutionResult(
                success=True,
                tx_id=f"paper_drift_long_{symbol}",
                filled_size=float(size),
                average_price=None,
                raw_response={
                    "executor": "drift_perp",
                    "mode": "paper",
                    "action": "open_long",
                    "symbol": symbol,
                    "size": float(size),
                    "metadata": metadata,
                },
            )

        if self.logger:
            self.logger.warning(
                "[DRIFT PERP] live mode requested but Drift live integration is not implemented yet"
            )

        return ExecutionResult(
            success=False,
            tx_id=None,
            filled_size=0.0,
            average_price=None,
            raw_response={
                "executor": "drift_perp",
                "mode": self.mode,
                "error": "Live Drift integration not implemented yet",
            },
        )

    async def execute_short(
        self,
        symbol: str,
        size: float,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ExecutionResult:
        metadata = metadata or {}

        if self.mode == "paper":
            if self.logger:
                self.logger.info(
                    "[DRIFT PERP][PAPER] open SHORT symbol=%s size=%s metadata=%s",
                    symbol,
                    size,
                    metadata,
                )

            return ExecutionResult(
                success=True,
                tx_id=f"paper_drift_short_{symbol}",
                filled_size=float(size),
                average_price=None,
                raw_response={
                    "executor": "drift_perp",
                    "mode": "paper",
                    "action": "open_short",
                    "symbol": symbol,
                    "size": float(size),
                    "metadata": metadata,
                },
            )

        if self.logger:
            self.logger.warning(
                "[DRIFT PERP] live mode requested but Drift live integration is not implemented yet"
            )

        return ExecutionResult(
            success=False,
            tx_id=None,
            filled_size=0.0,
            average_price=None,
            raw_response={
                "executor": "drift_perp",
                "mode": self.mode,
                "error": "Live Drift integration not implemented yet",
            },
        )

    async def close_position(
        self,
        symbol: str,
    ) -> ExecutionResult:
        if self.mode == "paper":
            if self.logger:
                self.logger.info(
                    "[DRIFT PERP][PAPER] close position symbol=%s",
                    symbol,
                )

            return ExecutionResult(
                success=True,
                tx_id=f"paper_drift_close_{symbol}",
                filled_size=0.0,
                average_price=None,
                raw_response={
                    "executor": "drift_perp",
                    "mode": "paper",
                    "action": "close_position",
                    "symbol": symbol,
                },
            )

        if self.logger:
            self.logger.warning(
                "[DRIFT PERP] live mode requested but Drift live integration is not implemented yet"
            )

        return ExecutionResult(
            success=False,
            tx_id=None,
            filled_size=0.0,
            average_price=None,
            raw_response={
                "executor": "drift_perp",
                "mode": self.mode,
                "error": "Live Drift integration not implemented yet",
            },
        )