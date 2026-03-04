from __future__ import annotations

from web3 import Web3

ERC20_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [{"name": "owner", "type": "address"}, {"name": "spender", "type": "address"}],
        "name": "allowance",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
    },
    {
        "constant": False,
        "inputs": [{"name": "spender", "type": "address"}, {"name": "amount", "type": "uint256"}],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
    },
    {"constant": True, "inputs": [], "name": "decimals", "outputs": [{"name": "", "type": "uint8"}], "type": "function"},
]


class ERC20:
    def __init__(self, w3: Web3, token_address: str):
        self.w3 = w3
        self.address = Web3.to_checksum_address(token_address)
        self.contract = self.w3.eth.contract(address=self.address, abi=ERC20_ABI)

    def balance_of(self, owner: str) -> int:
        return self.contract.functions.balanceOf(Web3.to_checksum_address(owner)).call()

    def allowance(self, owner: str, spender: str) -> int:
        return self.contract.functions.allowance(Web3.to_checksum_address(owner), Web3.to_checksum_address(spender)).call()

    def build_approve_tx(self, owner: str, spender: str, amount: int, nonce: int, chain_id: int) -> dict:
        return self.contract.functions.approve(
            Web3.to_checksum_address(spender),
            int(amount),
        ).build_transaction(
            {
                "from": Web3.to_checksum_address(owner),
                "nonce": int(nonce),
                "chainId": int(chain_id),
            }
        )