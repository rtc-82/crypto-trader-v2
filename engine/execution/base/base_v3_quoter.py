from __future__ import annotations

import logging


class BaseV3MathQuoter:
    """
    Deterministic spot-price quoter for Uniswap V3 pools.

    Why:
    - Full V3 swap math requires tick traversal (TickMath/SqrtPriceMath + tick data).
    - For micro sizing (your plan), spot-price quoting is stable and accurate enough.
    - Slippage protection will be enforced later during tx building.

    Output units:
    - quote_weth_to_usdc -> USDC (human)
    - quote_usdc_to_weth -> WETH (human)
    """

    def __init__(self, pool, logger: logging.Logger, fee: int = 3000):
        self.pool = pool
        self.logger = logger
        self.fee = fee  # 3000 = 0.3%

    def _fee_multiplier(self) -> float:
        return 1.0 - (self.fee / 1_000_000)

    def quote_weth_to_usdc(self, weth_amount: float) -> float:
        """
        Approx output using pool spot price (USDC per WETH) minus fee.
        """
        price_usdc_per_weth = float(self.pool.get_price())
        return float(weth_amount) * price_usdc_per_weth * self._fee_multiplier()

    def quote_usdc_to_weth(self, usdc_amount: float) -> float:
        """
        Approx output using pool spot price (USDC per WETH) minus fee.
        """
        price_usdc_per_weth = float(self.pool.get_price())
        if price_usdc_per_weth <= 0:
            raise RuntimeError("Invalid pool price (<= 0).")
        return (float(usdc_amount) / price_usdc_per_weth) * self._fee_multiplier()