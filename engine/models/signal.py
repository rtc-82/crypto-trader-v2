# sniper_crypto/v4_multichain_engine/models/signal.py

from dataclasses import dataclass


@dataclass
class Signal:
    direction: str
    atr: float