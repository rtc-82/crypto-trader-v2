from __future__ import annotations

import logging

from engine.execution.base.base_tokens import (
    get_token_config,
    get_trade_config,
)


class BaseV3MathQuoter:
    """
    Generic deterministic spot quoter for Base Uniswap V3 pairs.

    This uses spot-price math, which is appropriate for micro-size paper /
    early live testing when paired with a slippage guard.

    Conventions:
    - asset_symbol = traded token like AAVE / RENDER
    - quote_symbol = quote token from registry, usually USDC
    """

    def __init__(self, pool, logger: logging.Logger, fee: int = 3000):
        self.pool = pool
        self.logger = logger
        self.default_fee = int(fee)

    def _fee_multiplier(self, fee: int) -> float:
        return 1.0 - (int(fee) / 1_000_000.0)

    def _resolve_trade(self, asset_symbol: str) -> tuple[dict, dict, int]:
        asset_cfg = get_token_config(asset_symbol)
        trade_cfg = get_trade_config(asset_symbol)

        quote_symbol = trade_cfg.get("quote_symbol", "USDC")
        fee = int(trade_cfg.get("fee", self.default_fee))

        quote_cfg = get_token_config(quote_symbol)
        return asset_cfg, quote_cfg, fee

    def get_price_quote_per_asset(self, asset_symbol: str) -> float:
        asset_cfg, quote_cfg, fee = self._resolve_trade(asset_symbol)

        return float(
            self.pool.get_price(
                token_base=asset_cfg["address"],
                token_quote=quote_cfg["address"],
                base_decimals=asset_cfg["decimals"],
                quote_decimals=quote_cfg["decimals"],
                fee=fee,
            )
        )

    def quote_asset_to_quote(self, asset_symbol: str, asset_amount: float) -> float:
        _, _, fee = self._resolve_trade(asset_symbol)
        price_quote_per_asset = self.get_price_quote_per_asset(asset_symbol)
        return float(asset_amount) * price_quote_per_asset * self._fee_multiplier(fee)

    def quote_quote_to_asset(self, asset_symbol: str, quote_amount: float) -> float:
        _, _, fee = self._resolve_trade(asset_symbol)
        price_quote_per_asset = self.get_price_quote_per_asset(asset_symbol)

        if price_quote_per_asset <= 0:
            raise RuntimeError("Invalid pool price (<= 0).")

        return (float(quote_amount) / price_quote_per_asset) * self._fee_multiplier(fee)

    def estimate_quote_in_for_desired_asset_out(self, asset_symbol: str, desired_asset_out: float) -> float:
        """
        Approximate the quote-token input required to receive a desired asset output.
        """
        _, _, fee = self._resolve_trade(asset_symbol)
        price_quote_per_asset = self.get_price_quote_per_asset(asset_symbol)

        fee_mult = self._fee_multiplier(fee)
        if fee_mult <= 0:
            raise RuntimeError("Invalid fee multiplier (<= 0).")

        return (float(desired_asset_out) * price_quote_per_asset) / fee_mult