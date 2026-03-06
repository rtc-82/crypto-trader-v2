from __future__ import annotations

import json
from dataclasses import dataclass

from solana.rpc.async_api import AsyncClient

try:
    # solana-py now uses solders under the hood
    from solders.keypair import Keypair
    from solders.pubkey import Pubkey
except Exception:  # pragma: no cover
    Keypair = None  # type: ignore
    Pubkey = None  # type: ignore


LAMPORTS_PER_SOL = 1_000_000_000


@dataclass(frozen=True)
class SolanaWalletConfig:
    rpc_url: str
    keypair_path: str


class SolanaWallet:
    """
    Minimal Solana wallet wrapper:
    - Loads keypair from json file (array of ints)
    - Provides async RPC client
    - Returns SOL balance
    """

    def __init__(self, config: SolanaWalletConfig):
        if Keypair is None:
            raise RuntimeError(
                "Missing solders dependency. Install/update: python -m pip install solana"
            )

        self.config = config
        self.client = AsyncClient(config.rpc_url)
        self._keypair = self._load_keypair(config.keypair_path)

    @property
    def keypair(self) -> Keypair:
        return self._keypair

    @property
    def pubkey(self):
        return self._keypair.pubkey()

    async def get_sol_balance(self) -> float:
        resp = await self.client.get_balance(self.pubkey)
        lamports = int(resp.value)
        return lamports / LAMPORTS_PER_SOL

    async def close(self) -> None:
        await self.client.close()

    def _load_keypair(self, path: str) -> Keypair:
        with open(path, "r", encoding="utf-8") as f:
            secret = json.load(f)

        if not isinstance(secret, list) or len(secret) < 32:
            raise RuntimeError(f"Invalid Solana keypair file: {path}")

        secret_bytes = bytes(secret)
        return Keypair.from_bytes(secret_bytes)