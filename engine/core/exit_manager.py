# engine/core/exit_manager.py

from dataclasses import dataclass


@dataclass
class ExitDecision:
    should_exit: bool
    reason: str | None = None
    exit_price: float | None = None


class ExitManager:
    """
    Handles exit logic for open positions.
    """

    def __init__(self, atr_stop_multiplier=2.0, atr_take_multiplier=3.0):

        self.atr_stop_multiplier = atr_stop_multiplier
        self.atr_take_multiplier = atr_take_multiplier

    def evaluate_exit(self, direction, entry_price, current_price, atr):

        if atr is None:
            return ExitDecision(False)

        stop_distance = atr * self.atr_stop_multiplier
        take_distance = atr * self.atr_take_multiplier

        if direction == "LONG":

            stop = entry_price - stop_distance
            take = entry_price + take_distance

            if current_price <= stop:
                return ExitDecision(True, "STOP", stop)

            if current_price >= take:
                return ExitDecision(True, "TAKE_PROFIT", take)

        if direction == "SHORT":

            stop = entry_price + stop_distance
            take = entry_price - take_distance

            if current_price >= stop:
                return ExitDecision(True, "STOP", stop)

            if current_price <= take:
                return ExitDecision(True, "TAKE_PROFIT", take)

        return ExitDecision(False)