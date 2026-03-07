from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class Position:
    symbol: str
    direction: str
    entry_price: float
    size: float
    atr: float
    trailing_atr_mult: float
    best_price: float
    stop_loss: float
    entry_ts: int


class PositionManager:

    def __init__(self, max_concurrent_positions: int = 1):

        self.max_concurrent_positions = max_concurrent_positions
        self.positions: Dict[str, Position] = {}

    # ------------------------------------------------
    # PORTFOLIO STATE
    # ------------------------------------------------

    def has_open_position(self, symbol: Optional[str] = None):

        if symbol is None:
            return len(self.positions) > 0

        return symbol in self.positions

    def open_positions_count(self):

        return len(self.positions)

    def open_symbols(self):

        return list(self.positions.keys())

    def can_open_new(self):

        return len(self.positions) < self.max_concurrent_positions

    def all_positions(self):

        return list(self.positions.values())

    def get_position(self, symbol: str) -> Optional[Position]:

        return self.positions.get(symbol)

    def diagnostic_snapshot(self, symbol: str):

        p = self.positions.get(symbol)

        if p is None:
            return None

        return {
            "symbol": p.symbol,
            "direction": p.direction,
            "entry_price": float(p.entry_price),
            "size": float(p.size),
            "atr": float(p.atr),
            "trailing_atr_mult": float(p.trailing_atr_mult),
            "best_price": float(p.best_price),
            "stop_loss": float(p.stop_loss),
            "entry_ts": int(p.entry_ts),
        }

    # ------------------------------------------------
    # OPEN POSITION
    # ------------------------------------------------

    def open_position(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        size: float,
        atr: float,
        entry_ts: int,
        trailing_atr_mult: float = 2.0,
    ):

        if direction not in ("LONG", "SHORT"):
            raise ValueError(f"Invalid direction: {direction}")

        stop_loss = (
            entry_price - atr * trailing_atr_mult
            if direction == "LONG"
            else entry_price + atr * trailing_atr_mult
        )

        self.positions[symbol] = Position(
            symbol=symbol,
            direction=direction,
            entry_price=float(entry_price),
            size=float(size),
            atr=float(atr),
            trailing_atr_mult=float(trailing_atr_mult),
            best_price=float(entry_price),
            stop_loss=float(stop_loss),
            entry_ts=int(entry_ts),
        )

    # ------------------------------------------------
    # CLOSE POSITION
    # ------------------------------------------------

    def close_position(self, symbol):

        return self.positions.pop(symbol, None)

    # ------------------------------------------------
    # TRAILING STOP UPDATE
    # ------------------------------------------------

    def _update_trailing_stop(self, p: Position, high: float, low: float):

        if p.direction == "LONG":

            if high > p.best_price:
                p.best_price = float(high)

            trail_stop = p.best_price - (p.trailing_atr_mult * p.atr)

            if trail_stop > p.stop_loss:
                p.stop_loss = float(trail_stop)

        else:

            if low < p.best_price:
                p.best_price = float(low)

            trail_stop = p.best_price + (p.trailing_atr_mult * p.atr)

            if trail_stop < p.stop_loss:
                p.stop_loss = float(trail_stop)

    # ------------------------------------------------
    # EXIT CHECK
    # ------------------------------------------------

    def check_exit(self, symbol: str, high: float, low: float):

        p = self.positions.get(symbol)

        if p is None:
            return None

        pre_stop_loss = float(p.stop_loss)
        pre_best_price = float(p.best_price)

        self._update_trailing_stop(p, high, low)

        post_stop_loss = float(p.stop_loss)
        post_best_price = float(p.best_price)

        diagnostic = {
            "symbol": p.symbol,
            "direction": p.direction,
            "entry_price": float(p.entry_price),
            "size": float(p.size),
            "atr": float(p.atr),
            "trailing_atr_mult": float(p.trailing_atr_mult),
            "high": float(high),
            "low": float(low),
            "pre_stop_loss": pre_stop_loss,
            "post_stop_loss": post_stop_loss,
            "pre_best_price": pre_best_price,
            "post_best_price": post_best_price,
        }

        if p.direction == "LONG":

            if low <= p.stop_loss:
                exit_price = p.stop_loss
                return {
                    "result": "STOP",
                    "exit_price": float(exit_price),
                    "position": p,
                    "diagnostic": diagnostic,
                }

        else:

            if high >= p.stop_loss:
                exit_price = p.stop_loss
                return {
                    "result": "STOP",
                    "exit_price": float(exit_price),
                    "position": p,
                    "diagnostic": diagnostic,
                }

        return None

    # ------------------------------------------------
    # R MULTIPLE
    # ------------------------------------------------

    @staticmethod
    def r_multiple(entry_price, exit_price, stop_loss, direction):

        entry_price = float(entry_price)
        exit_price = float(exit_price)
        stop_loss = float(stop_loss)

        if direction == "LONG":

            risk = entry_price - stop_loss

            if risk <= 0:
                return 0.0

            return (exit_price - entry_price) / risk

        if direction == "SHORT":

            risk = stop_loss - entry_price

            if risk <= 0:
                return 0.0

            return (entry_price - exit_price) / risk

        raise ValueError(f"Invalid direction: {direction}")