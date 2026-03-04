from __future__ import annotations

import logging


class TxSigner:
    """
    Signs and (optionally) broadcasts transactions using BaseWeb3Provider.
    """

    def __init__(self, provider, logger: logging.Logger):
        self.provider = provider
        self.logger = logger

    def sign(self, tx: dict):
        signed = self.provider.sign_transaction(tx)
        self.logger.info("Transaction signed.")
        return signed

    def send(self, signed_tx) -> str:
        tx_hash = self.provider.send_raw_transaction(signed_tx)
        self.logger.info(f"Transaction broadcasted: {tx_hash}")
        return tx_hash