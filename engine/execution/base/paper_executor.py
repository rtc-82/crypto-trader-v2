from __future__ import annotations

import logging


class PaperExecutor:
    def __init__(self, cfg, logger: logging.Logger):
        self.cfg = cfg
        self.logger = logger

    async def open_position(self, direction: str, price: float) -> dict:
        self.logger.info(f"[PAPER] OPEN {direction} @ {price}")
        return {"status": "ok", "mode": "paper", "action": "open", "direction": direction, "price": price}

    async def close_position(self, direction: str, price: float) -> dict:
        self.logger.info(f"[PAPER] CLOSE {direction} @ {price}")
        return {"status": "ok", "mode": "paper", "action": "close", "direction": direction, "price": price}