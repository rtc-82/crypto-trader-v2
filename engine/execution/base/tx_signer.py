from __future__ import annotations

import logging


class TxSigner:
    def __init__(self, provider, logger: logging.Logger):
        self.provider = provider
        self.logger = logger

    def sign(self, tx: dict):
        signed = self.provider.sign_transaction(tx)
        self.logger.info("Transaction signed.")
        return signed

    def send(self, signed_tx) -> str:
        try:
            tx_hash = self.provider.send_raw_transaction(signed_tx)
        except Exception as e:
            self.logger.exception(f"Transaction broadcast failed: {e}")
            raise

        self.logger.info(f"Transaction broadcasted: {tx_hash}")
        return tx_hash

    def sign_and_send(self, tx: dict, label: str = "TX") -> str:
        signed_tx = self.sign(tx)
        try:
            tx_hash = self.provider.send_raw_transaction(signed_tx)
        except Exception as e:
            self.logger.exception(f"{label} broadcast failed: {e}")
            raise

        self.logger.info(f"{label} broadcast: {tx_hash}")
        return tx_hash
