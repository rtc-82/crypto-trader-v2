from abc import ABC, abstractmethod
from ..models.signal import Signal


class AbstractExecutor(ABC):

    @abstractmethod
    async def execute_trade(self, signal: Signal, amount: int) -> dict:
        pass