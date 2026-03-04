from dataclasses import dataclass


@dataclass
class Position:
    direction: str
    entry_price: float
    stop_loss: float
    atr: float
    trailing_atr_mult: float
    best_price: float  # highest (long) / lowest (short) since entry


class PositionManager:
    def __init__(self):
        self.position: Position | None = None

    def has_position(self) -> bool:
        return self.position is not None

    def open_position(
        self,
        direction: str,
        entry_price: float,
        stop_loss: float,
        atr: float,
        trailing_atr_mult: float = 2.0,
    ):
        """
        Opens a position with:
        - initial stop_loss (usually ATR-based)
        - trailing stop that follows best_price by trailing_atr_mult * ATR
        """
        if direction not in ("LONG", "SHORT"):
            raise ValueError(f"Invalid direction: {direction}")

        best_price = entry_price
        self.position = Position(
            direction=direction,
            entry_price=float(entry_price),
            stop_loss=float(stop_loss),
            atr=float(atr),
            trailing_atr_mult=float(trailing_atr_mult),
            best_price=float(best_price),
        )

    def close_position(self):
        self.position = None

    def _update_trailing_stop(self, high: float, low: float):
        """
        Ratchets stop in favorable direction only.
        """
        p = self.position
        if p is None:
            return

        if p.direction == "LONG":
            # update best (highest) price
            if high > p.best_price:
                p.best_price = float(high)

            # trailing stop follows best_price
            trail_stop = p.best_price - (p.trailing_atr_mult * p.atr)

            # ratchet only upwards
            if trail_stop > p.stop_loss:
                p.stop_loss = float(trail_stop)

        else:  # SHORT
            # update best (lowest) price
            if low < p.best_price:
                p.best_price = float(low)

            # trailing stop follows best_price
            trail_stop = p.best_price + (p.trailing_atr_mult * p.atr)

            # ratchet only downwards (for shorts stop moves down)
            if trail_stop < p.stop_loss:
                p.stop_loss = float(trail_stop)

    def check_exit(self, high: float, low: float):
        """
        Exit logic:
        - Update trailing stop each candle
        - Exit only on stop hit (trailing stop)
        Returns dict or None.

        dict = {
          "result": "STOP",
          "exit_price": float,
        }
        """
        p = self.position
        if p is None:
            return None

        # 1) update trailing stop based on new candle extremes
        self._update_trailing_stop(high, low)

        # 2) check stop hit
        if p.direction == "LONG":
            # if low breaches stop, assume stop filled at stop_loss
            if low <= p.stop_loss:
                exit_price = p.stop_loss
                self.close_position()
                return {"result": "STOP", "exit_price": float(exit_price)}

        else:  # SHORT
            if high >= p.stop_loss:
                exit_price = p.stop_loss
                self.close_position()
                return {"result": "STOP", "exit_price": float(exit_price)}

        return None

    @staticmethod
    def r_multiple(entry_price: float, exit_price: float, stop_loss: float, direction: str) -> float:
        """
        Compute realized R using initial risk distance (entry - stop at entry time).

        For LONG:
          risk = entry - initial_stop
          R = (exit - entry) / risk

        For SHORT:
          risk = initial_stop - entry
          R = (entry - exit) / risk
        """
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