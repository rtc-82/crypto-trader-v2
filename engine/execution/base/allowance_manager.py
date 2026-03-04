from __future__ import annotations

import logging
from web3 import Web3

from engine.execution.base.erc20 import ERC20


class AllowanceManager:
    """
    Checks ERC20 allowance and builds approve tx when needed.
    """

    def __init__(self, provider, logger: logging.Logger):
        self.provider = provider
        self.logger = logger
        self.w3 = provider.w3

    def get_allowance(self, token_address: str, owner: str, spender: str) -> int:
        token = ERC20(self.w3, token_address)
        return token.allowance(owner, spender)

    def needs_approval(self, token_address: str, owner: str, spender: str, required_amount: int) -> bool:
        current = self.get_allowance(token_address, owner, spender)
        self.logger.info(f"Allowance: {current} | Required: {required_amount}")
        return current < required_amount

    def build_approve_tx(
        self,
        token_address: str,
        spender: str,
        amount: int,
        gas_limit: int = 80_000,
        try_estimate_gas: bool = False,
    ) -> dict:
        token = ERC20(self.w3, token_address)

        tx = token.build_approve_tx(
            owner=self.provider.address,
            spender=Web3.to_checksum_address(spender),
            amount=int(amount),
            nonce=self.provider.get_nonce(),
            chain_id=self.provider.chain_id,
        )

        # fees
        try:
            tx.update(self.provider.get_eip1559_fees())
        except Exception:
            tx["gasPrice"] = self.provider.get_gas_price_wei()

        tx["gas"] = int(gas_limit)

        if try_estimate_gas:
            try:
                tx["gas"] = int(self.w3.eth.estimate_gas(tx))
                self.logger.info(f"Approve gas estimated: {tx['gas']}")
            except Exception as e:
                self.logger.warning(f"Approve gas estimate failed (using {gas_limit}): {e}")

        return tx