# engine/core/signal.py

from dataclasses import dataclass


@dataclass
class Signal:
    direction: str
    atr: float