from __future__ import annotations

from abc import ABC, abstractmethod


class AbstractExecutor(ABC):
    @abstractmethod
    async def open_position(self, direction: str, price: float) -> dict:
        raise NotImplementedError

    @abstractmethod
    async def close_position(self, direction: str, price: float) -> dict:
        raise NotImplementedError