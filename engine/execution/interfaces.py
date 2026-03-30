from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class ExecutionResult:
    success: bool
    tx_id: Optional[str] = None
    executed_size: Optional[float] = None
    avg_price: Optional[float] = None
    status: Optional[str] = None
    error: Optional[str] = None
    raw: Any = None


class LiveExecutorInterface(ABC):
    @abstractmethod
    async def execute_trade(
        self,
        symbol: str,
        direction: str,
        size: float,
    ) -> ExecutionResult:
        raise NotImplementedError