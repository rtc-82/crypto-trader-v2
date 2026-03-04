from __future__ import annotations

import logging
from .abstract_executor import AbstractExecutor


class LiveExecutorAdapter(AbstractExecutor):
    """
    Routes execution to paper or live executor depending on mode.
    """
    def __init__(self, mode: str, paper_executor: AbstractExecutor, live_executor: AbstractExecutor | None, logger: logging.Logger):
        self.mode = mode
        self.paper = paper_executor
        self.live = live_executor
        self.logger = logger

    async def open_position(self, direction: str, price: float) -> dict:
        if self.mode == "live":
            if not self.live:
                raise RuntimeError("Live mode enabled but no live executor configured.")
            return await self.live.open_position(direction, price)
        return await self.paper.open_position(direction, price)

    async def close_position(self, direction: str, price: float) -> dict:
        if self.mode == "live":
            if not self.live:
                raise RuntimeError("Live mode enabled but no live executor configured.")
            return await self.live.close_position(direction, price)
        return await self.paper.close_position(direction, price)