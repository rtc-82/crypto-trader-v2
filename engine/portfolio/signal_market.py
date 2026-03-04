from dataclasses import dataclass
from typing import List


@dataclass
class SignalCandidate:

    symbol: str
    direction: str
    price: float
    atr: float

    slope_norm: float
    vol_percentile: float

    score: float = 0.0


class SignalMarket:

    def __init__(self):

        self.signals: List[SignalCandidate] = []

    def clear(self):

        self.signals = []

    def add_signal(
        self,
        symbol,
        direction,
        price,
        atr,
        slope_norm,
        vol_percentile
    ):

        score = (
            0.6 * abs(slope_norm)
            + 0.4 * vol_percentile
        )

        signal = SignalCandidate(
            symbol,
            direction,
            price,
            atr,
            slope_norm,
            vol_percentile,
            score
        )

        self.signals.append(signal)

    def best_signal(self):

        if not self.signals:
            return None

        return max(self.signals, key=lambda s: s.score)