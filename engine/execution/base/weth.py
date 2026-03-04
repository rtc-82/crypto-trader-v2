from __future__ import annotations

import logging
from web3 import Web3

WETH = Web3.to_checksum_address("0x4200000000000000000000000000000000000006")

WETH_ABI = [
    {
        "inputs": [],
        "name": "deposit",
        "outputs": [],
        "stateMutability": "payable",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "uint256", "name": "wad", "type": "uint256"}],
        "name": "withdraw",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]


class WETHWrapper:
    """
    Builds WETH wrap/unwrap txs.
    - deposit(): send ETH to WETH contract, receive WETH
    - withdraw(): burn WETH, receive ETH
    """

    def __init__(self, provider, logger: logging.Logger):
        self.provider = provider
        self.logger = logger
        self.w3 = provider.w3
        self.contract = self.w3.eth.contract(address=WETH, abi=WETH_ABI)

    def build_wrap_tx(
        self,
        amount_eth: float,
        gas_limit: int = 120_000,
        try_estimate_gas: bool = False,
    ) -> dict:
        value_wei = int(amount_eth * 10**18)

        data = self.contract.functions.deposit()._encode_transaction_data()

        tx: dict = {
            "to": WETH,
            "from": self.provider.address,
            "data": data,
            "value": value_wei,
            "nonce": self.provider.get_nonce(),
            "chainId": self.provider.chain_id,
            "gas": int(gas_limit),
        }

        try:
            tx.update(self.provider.get_eip1559_fees())
        except Exception:
            tx["gasPrice"] = self.provider.get_gas_price_wei()

        if try_estimate_gas:
            try:
                tx["gas"] = int(self.w3.eth.estimate_gas(tx))
            except Exception as e:
                self.logger.warning(f"WETH wrap gas estimate failed (using {gas_limit}): {e}")

        return tx

    def build_unwrap_tx(
        self,
        amount_weth_wei: int,
        gas_limit: int = 120_000,
        try_estimate_gas: bool = False,
    ) -> dict:
        data = self.contract.functions.withdraw(int(amount_weth_wei))._encode_transaction_data()

        tx: dict = {
            "to": WETH,
            "from": self.provider.address,
            "data": data,
            "value": 0,
            "nonce": self.provider.get_nonce(),
            "chainId": self.provider.chain_id,
            "gas": int(gas_limit),
        }

        try:
            tx.update(self.provider.get_eip1559_fees())
        except Exception:
            tx["gasPrice"] = self.provider.get_gas_price_wei()

        if try_estimate_gas:
            try:
                tx["gas"] = int(self.w3.eth.estimate_gas(tx))
            except Exception as e:
                self.logger.warning(f"WETH unwrap gas estimate failed (using {gas_limit}): {e}")

        return tx