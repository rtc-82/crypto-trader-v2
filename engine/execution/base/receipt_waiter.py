from __future__ import annotations

import time
import logging


class ReceiptWaiter:
    """
    Waits for a transaction receipt to appear.
    """

    def __init__(self, provider, logger: logging.Logger):
        self.provider = provider
        self.logger = logger
        self.w3 = provider.w3

    def wait(self, tx_hash: str, timeout_sec: int = 180, poll_sec: float = 2.0) -> dict:
        start = time.time()

        while True:
            try:
                receipt = self.w3.eth.get_transaction_receipt(tx_hash)
            except Exception:
                receipt = None

            if receipt is not None:
                return dict(receipt)

            if time.time() - start > timeout_sec:
                raise TimeoutError(f"Timed out waiting for receipt: {tx_hash}")

            time.sleep(poll_sec)