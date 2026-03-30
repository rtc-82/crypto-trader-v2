from __future__ import annotations

from typing import Dict, Any, Optional

from engine.execution.interfaces import (
    LiveExecutorInterface,
    ExecutionResult,
)


class PaperPerpExecutor(LiveExecutorInterface):
    """
    Generic paper-only perp executor.

    This does not connect to a real perp venue.
    It exists so the engine can route SHORT signals to a proper
    paper execution layer instead of using spot swaps.

    symbol:
        venue market identifier, e.g. "PYTH-PERP", "AAVE-PERP"
    direction:
        LONG or SHORT
    size:
        human units from the current engine sizing path
    """

    def __init__(self, venue_name: str, mode: str = "paper"):
        self.venue_name = venue_name
        self.mode = mode

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

        if self.mode != "paper":
            return ExecutionResult(
                success=False,
                tx_id=None,
                filled_size=0.0,
                average_price=None,
                raw_response={
                    "error": f"{self.venue_name} paper perp executor is not live-enabled yet",
                    "symbol": symbol,
                    "direction": direction,
                    "size": size,
                },
            )

        return ExecutionResult(
            success=True,
            tx_id=f"{self.venue_name.lower()}_paper_tx",
            filled_size=float(size),
            average_price=None,
            raw_response={
                "venue": self.venue_name,
                "mode": self.mode,
                "symbol": symbol,
                "direction": direction,
                "size": float(size),
                "metadata": metadata,
            },
        )