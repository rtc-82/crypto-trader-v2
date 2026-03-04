from __future__ import annotations

import logging


class SlippageGuard:
    """
    Converts an expected output into a minimum output given slippage tolerance.
    """

    def __init__(self, logger: logging.Logger, slippage_bps: int = 50):
        self.logger = logger
        self.slippage_bps = slippage_bps  # 50 = 0.50%

    def min_out(self, expected_out: float) -> float:
        if expected_out <= 0:
            raise ValueError("expected_out must be > 0")

        slip = self.slippage_bps / 10_000.0
        minimum = expected_out * (1.0 - slip)

        self.logger.info(
            f"SlippageGuard: expected={expected_out:.8f} min={minimum:.8f} (slippage_bps={self.slippage_bps})"
        )
        return minimum