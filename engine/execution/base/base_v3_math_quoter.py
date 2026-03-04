from __future__ import annotations

import logging


class BaseV3MathQuoter:
    """
    Deterministic SPOT-price quoter for Uniswap V3 pools (Base).

    This intentionally avoids full tick-traversal math.
    For micro-size trades, spot quoting + slippage guard is the right baseline.

    - quote_weth_to_usdc -> returns USDC (human)
    - quote_usdc_to_weth -> returns WETH (human)
    """

    def __init__(self, pool, logger: logging.Logger, fee: int = 3000):
        self.pool = pool
        self.logger = logger
        self.fee = fee  # 3000 = 0.3%

    def _fee_multiplier(self) -> float:
        return 1.0 - (self.fee / 1_000_000.0)

    def quote_weth_to_usdc(self, weth_amount: float) -> float:
        price_usdc_per_weth = float(self.pool.get_price())
        out = float(weth_amount) * price_usdc_per_weth * self._fee_multiplier()
        return out

    def quote_usdc_to_weth(self, usdc_amount: float) -> float:
        price_usdc_per_weth = float(self.pool.get_price())
        if price_usdc_per_weth <= 0:
            raise RuntimeError("Invalid pool price (<= 0).")
        out = (float(usdc_amount) / price_usdc_per_weth) * self._fee_multiplier()
        return out