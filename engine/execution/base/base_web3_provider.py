from __future__ import annotations

from web3 import Web3
from eth_account import Account
from dotenv import load_dotenv
import os
import logging


class BaseWeb3Provider:
    """
    Base Mainnet Web3 Provider

    Responsibilities:
    - Connect to Base RPC
    - Validate chain ID
    - Load trading wallet
    - Provide gas + nonce utilities
    - Prepare for transaction signing
    """

    EXPECTED_CHAIN_ID = 8453  # Base Mainnet

    def __init__(self, logger: logging.Logger):
        load_dotenv()

        self.logger = logger
        self.rpc_url = os.getenv("BASE_RPC_URL")
        self.private_key = os.getenv("BASE_PRIVATE_KEY")

        if not self.rpc_url:
            raise RuntimeError("BASE_RPC_URL missing in .env")

        if not self.private_key:
            raise RuntimeError("BASE_PRIVATE_KEY missing in .env")

        # Initialize Web3
        self.w3 = Web3(Web3.HTTPProvider(self.rpc_url))

        if not self.w3.is_connected():
            raise RuntimeError("Failed to connect to Base RPC.")

        # Validate chain
        self.chain_id = self.w3.eth.chain_id
        if self.chain_id != self.EXPECTED_CHAIN_ID:
            raise RuntimeError(
                f"Connected to wrong chain. Expected {self.EXPECTED_CHAIN_ID}, got {self.chain_id}"
            )

        # Load wallet
        self.account = Account.from_key(self.private_key)
        self.address = Web3.to_checksum_address(self.account.address)

        self.logger.info("Base RPC connected successfully.")
        self.logger.info(f"Chain ID: {self.chain_id}")
        self.logger.info(f"Wallet: {self.address}")

    # ==========================================================
    # Wallet Utilities
    # ==========================================================

    def get_balance_eth(self) -> float:
        """Return wallet ETH balance."""
        balance_wei = self.w3.eth.get_balance(self.address)
        return float(self.w3.from_wei(balance_wei, "ether"))

    def get_balance_wei(self) -> int:
        """Return wallet ETH balance in wei."""
        return self.w3.eth.get_balance(self.address)

    def get_nonce(self) -> int:
        """Return current transaction nonce."""
        return self.w3.eth.get_transaction_count(self.address)

    # ==========================================================
    # Gas Utilities
    # ==========================================================

    def get_gas_price_wei(self) -> int:
        """Return current gas price (legacy)."""
        return self.w3.eth.gas_price

    def get_gas_price_gwei(self) -> float:
        return self.get_gas_price_wei() / 1_000_000_000

    def get_eip1559_fees(self) -> dict:
        """
        Return EIP-1559 fee structure.
        Base supports this.
        """
        latest_block = self.w3.eth.get_block("latest")

        base_fee = latest_block.get("baseFeePerGas", 0)
        priority_fee = self.w3.to_wei(0.01, "gwei")  # conservative

        max_fee = base_fee + priority_fee

        return {
            "maxFeePerGas": max_fee,
            "maxPriorityFeePerGas": priority_fee,
        }

    # ==========================================================
    # Transaction Signing
    # ==========================================================

    def sign_transaction(self, tx: dict):
        """Sign a transaction dict."""
        return self.account.sign_transaction(tx)

    def send_raw_transaction(self, signed_tx):
        """Send signed transaction to network."""
        tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
        return tx_hash.hex()