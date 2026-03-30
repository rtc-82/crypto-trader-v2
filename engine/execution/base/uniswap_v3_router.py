from __future__ import annotations

import time
import logging
from typing import Optional
from web3 import Web3

SWAP_ROUTER = Web3.to_checksum_address("0x2626664c2603336E57B271c5C0b26F421741e481")

WETH = Web3.to_checksum_address("0x4200000000000000000000000000000000000006")
USDC = Web3.to_checksum_address("0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

ROUTER_ABI = [
    {
        "inputs": [
            {
                "components": [
                    {"internalType": "address", "name": "tokenIn", "type": "address"},
                    {"internalType": "address", "name": "tokenOut", "type": "address"},
                    {"internalType": "uint24", "name": "fee", "type": "uint24"},
                    {"internalType": "address", "name": "recipient", "type": "address"},
                    {"internalType": "uint256", "name": "deadline", "type": "uint256"},
                    {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
                    {"internalType": "uint256", "name": "amountOutMinimum", "type": "uint256"},
                    {"internalType": "uint160", "name": "sqrtPriceLimitX96", "type": "uint160"},
                ],
                "internalType": "struct ISwapRouter.ExactInputSingleParams",
                "name": "params",
                "type": "tuple",
            }
        ],
        "name": "exactInputSingle",
        "outputs": [{"internalType": "uint256", "name": "amountOut", "type": "uint256"}],
        "stateMutability": "payable",
        "type": "function",
    }
]


class UniswapV3Router:
    """
    Generic exactInputSingle tx builder.
    """

    def __init__(self, provider, logger: logging.Logger, fee: int = 3000):
        self.provider = provider
        self.logger = logger
        self.w3 = provider.w3
        self.fee = int(fee)
        self.contract = self.w3.eth.contract(address=SWAP_ROUTER, abi=ROUTER_ABI)

    def build_exact_input_single_tx(
        self,
        token_in: str,
        token_out: str,
        amount_in: int,
        min_out: int,
        recipient: str,
        deadline_seconds: int = 120,
        value_wei: int = 0,
        gas_limit: int = 300_000,
        try_estimate_gas: bool = False,
        fee: Optional[int] = None,
    ) -> dict:
        swap_fee = int(self.fee if fee is None else fee)
        deadline = int(time.time()) + int(deadline_seconds)

        params = (
            Web3.to_checksum_address(token_in),
            Web3.to_checksum_address(token_out),
            swap_fee,
            Web3.to_checksum_address(recipient),
            deadline,
            int(amount_in),
            int(min_out),
            0,
        )

        data = self.contract.functions.exactInputSingle(params)._encode_transaction_data()

        tx: dict = {
            "to": SWAP_ROUTER,
            "from": self.provider.address,
            "data": data,
            "value": int(value_wei),
            "nonce": self.provider.get_nonce(),
            "chainId": self.provider.chain_id,
            "gas": int(gas_limit),
        }

        try:
            fees = self.provider.get_eip1559_fees()
            tx.update(fees)
        except Exception:
            tx["gasPrice"] = self.provider.get_gas_price_wei()

        if try_estimate_gas:
            try:
                est = self.w3.eth.estimate_gas(tx)
                tx["gas"] = int(est)
                self.logger.info("Gas estimated successfully: %s", est)
            except Exception as e:
                self.logger.warning(
                    "Gas estimation failed (using placeholder %s): %s",
                    gas_limit,
                    e,
                )

        return tx

    def build_weth_to_usdc_tx(
        self,
        amount_in_wei: int,
        min_out_usdc: int,
        recipient: str,
        **kwargs,
    ) -> dict:
        return self.build_exact_input_single_tx(
            token_in=WETH,
            token_out=USDC,
            amount_in=amount_in_wei,
            min_out=min_out_usdc,
            recipient=recipient,
            value_wei=0,
            **kwargs,
        )

    def build_usdc_to_weth_tx(
        self,
        amount_in_usdc: int,
        min_out_wei: int,
        recipient: str,
        **kwargs,
    ) -> dict:
        return self.build_exact_input_single_tx(
            token_in=USDC,
            token_out=WETH,
            amount_in=amount_in_usdc,
            min_out=min_out_wei,
            recipient=recipient,
            value_wei=0,
            **kwargs,
        )