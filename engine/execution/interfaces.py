# engine/execution/interfaces.py

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Any


# ==========================================================
# STANDARDIZED EXECUTION RESULT
# ==========================================================

@dataclass
class ExecutionResult:
    success: bool
    tx_id: str | None
    filled_size: float
    average_price: float | None
    raw_response: Dict[str, Any] | None = None


# ==========================================================
# EXECUTOR INTERFACE CONTRACT
# ==========================================================

class LiveExecutorInterface(ABC):
    """
    All chain executors MUST implement this interface.

    The core engine never talks to Solana/Web3 directly.
    It only talks to this contract.
    """

    @abstractmethod
    async def execute_long(
        self,
        symbol: str,
        size: float,
        metadata: Dict[str, Any],
    ) -> ExecutionResult:
        pass

    @abstractmethod
    async def execute_short(
        self,
        symbol: str,
        size: float,
        metadata: Dict[str, Any],
    ) -> ExecutionResult:
        pass

    @abstractmethod
    async def close_position(
        self,
        symbol: str,
    ) -> ExecutionResult:
        pass

    @abstractmethod
    async def get_balance(self) -> float:
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        pass