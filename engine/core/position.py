import logging
from dataclasses import dataclass
from typing import Dict, List

logger = logging.getLogger("trading_engine")


# ------------------------------------------------
# POSITION MODEL
# ------------------------------------------------

@dataclass
class Position:

    symbol: str
    direction: str
    entry_price: float
    size: float
    atr: float
    stop_loss: float
    entry_ts: int


# ------------------------------------------------
# POSITION MANAGER
# ------------------------------------------------

class PositionManager:

    def __init__(self, max_concurrent_positions: int = 5):

        self.max_concurrent_positions = max_concurrent_positions

        self.positions: Dict[str, Position] = {}

        logger.info(
            f"[POSITION MANAGER] max_positions={self.max_concurrent_positions}"
        )

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
    ):

        if symbol in self.positions:
            logger.warning(f"[POSITION] Already open: {symbol}")
            return

        if len(self.positions) >= self.max_concurrent_positions:
            logger.warning("[POSITION] Max concurrent positions reached")
            return

        # Stop distance based on ATR
        stop_distance = atr * 1.5

        if direction.lower() == "long":
            stop_loss = entry_price - stop_distance
        else:
            stop_loss = entry_price + stop_distance

        position = Position(
            symbol=symbol,
            direction=direction.lower(),
            entry_price=entry_price,
            size=size,
            atr=atr,
            stop_loss=stop_loss,
            entry_ts=entry_ts,
        )

        self.positions[symbol] = position

        logger.info(
            f"[POSITION OPEN] {symbol} {direction} "
            f"entry={entry_price} size={size}"
        )

    # ------------------------------------------------
    # CLOSE POSITION
    # ------------------------------------------------

    def close_position(self, symbol: str):

        if symbol not in self.positions:
            logger.warning(f"[POSITION] Attempted close but not found: {symbol}")
            return

        del self.positions[symbol]

        logger.info(f"[POSITION CLOSED] {symbol}")

    # ------------------------------------------------
    # GET OPEN SYMBOLS
    # ------------------------------------------------

    def open_symbols(self) -> List[str]:
        return list(self.positions.keys())

    # ------------------------------------------------
    # POSITION COUNT
    # ------------------------------------------------

    def open_positions_count(self) -> int:
        return len(self.positions)

    # ------------------------------------------------
    # RETURN ALL POSITIONS
    # ------------------------------------------------

    def all_positions(self) -> List[Position]:
        return list(self.positions.values())

    # ------------------------------------------------
    # R MULTIPLE CALCULATION
    # ------------------------------------------------

    def r_multiple(
        self,
        entry_price: float,
        exit_price: float,
        stop_loss: float,
        direction: str,
    ) -> float:

        try:

            risk = abs(entry_price - stop_loss)

            if risk == 0:
                return 0.0

            if direction == "long":

                reward = exit_price - entry_price

            else:

                reward = entry_price - exit_price

            r = reward / risk

            return round(r, 4)

        except Exception as e:

            logger.error(f"[R MULTIPLE ERROR] {e}")
            return 0.0