from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, Optional
import json
import os
from datetime import datetime


# ==========================================================
# STATE MODELS (v2.1)
# ==========================================================

@dataclass
class PositionState:
    chain: str
    symbol: str
    direction: str  # "LONG" / "SHORT"
    entry_price: float
    size: float
    unrealized_pnl: float = 0.0


@dataclass
class PortfolioState:
    total_equity: float
    peak_equity: float
    last_reset_day: Optional[str]

    realized_pnl: float
    daily_realized_pnl: float

    # key format: "{chain}:{symbol}"
    positions: Dict[str, PositionState]


# ==========================================================
# CAPITAL ACCOUNTING ENGINE
# ==========================================================

class CapitalAccounting:
    """
    Tracks equity as:
      total_equity = initial_equity + realized_pnl + sum(unrealized_pnl of open positions)

    Positions are keyed by (chain, symbol) to avoid chain-price ambiguity and allow multiple
    concurrent positions per chain.
    """

    def __init__(
        self,
        initial_equity: float,
        chains: list[str],
        state_file: str = "engine_state.json",
    ):
        self.initial_equity = float(initial_equity)
        self.state_file = state_file
        self._chains = list(chains)

        if os.path.exists(self.state_file):
            try:
                self.state = self._load_state_with_migration()
            except Exception:
                self.state = self._new_state()
        else:
            self.state = self._new_state()

        # Always write state on startup (crash-safe, ensures file exists)
        self._save_state()

    def _new_state(self) -> PortfolioState:
        return PortfolioState(
            total_equity=self.initial_equity,
            peak_equity=self.initial_equity,
            last_reset_day=None,
            realized_pnl=0.0,
            daily_realized_pnl=0.0,
            positions={},
        )

    # ==========================================================
    # EQUITY
    # ==========================================================

    @property
    def equity(self) -> float:
        return float(self.state.total_equity)

    def _recompute_total_equity(self) -> None:
        remaining_unrealized = sum(
            float(pos.unrealized_pnl) for pos in self.state.positions.values()
        )

        self.state.total_equity = (
            self.initial_equity
            + float(self.state.realized_pnl)
            + float(remaining_unrealized)
        )

        if self.state.total_equity > self.state.peak_equity:
            self.state.peak_equity = self.state.total_equity

    # ==========================================================
    # MARK TO MARKET
    # ==========================================================

    def mark_to_market(self, price_map: Dict[str, float]) -> None:
        """
        price_map is symbol-keyed, e.g.:
          {"BTCUSDT": 65000.0, "ETHUSDT": 3400.0}
        """

        total_unrealized = 0.0

        for _, pos in self.state.positions.items():
            price = price_map.get(pos.symbol)
            if price is None:
                # no update if we don't have a fresh price
                total_unrealized += float(pos.unrealized_pnl)
                continue

            if pos.direction == "LONG":
                pnl = (price - pos.entry_price) * pos.size
            else:
                pnl = (pos.entry_price - price) * pos.size

            pos.unrealized_pnl = float(pnl)
            total_unrealized += float(pnl)

        self.state.total_equity = (
            self.initial_equity
            + float(self.state.realized_pnl)
            + float(total_unrealized)
        )

        if self.state.total_equity > self.state.peak_equity:
            self.state.peak_equity = self.state.total_equity

        self._save_state()

    # ==========================================================
    # POSITION MANAGEMENT
    # ==========================================================

    def open_position(
        self,
        chain: str,
        symbol: str,
        direction: str,
        entry_price: float,
        size: float,
    ) -> None:
        key = f"{chain}:{symbol}"

        if key in self.state.positions:
            raise ValueError(f"Position already exists for {key}")

        self.state.positions[key] = PositionState(
            chain=chain,
            symbol=symbol,
            direction=direction.upper(),
            entry_price=float(entry_price),
            size=float(size),
            unrealized_pnl=0.0,
        )

        self._recompute_total_equity()
        self._save_state()

    def close_position(
        self,
        chain: str,
        symbol: str,
        exit_price: float,
    ) -> float:
        key = f"{chain}:{symbol}"
        pos = self.state.positions.get(key)

        if not pos:
            return 0.0

        if pos.direction == "LONG":
            pnl = (float(exit_price) - pos.entry_price) * pos.size
        else:
            pnl = (pos.entry_price - float(exit_price)) * pos.size

        self.state.realized_pnl += float(pnl)
        self.state.daily_realized_pnl += float(pnl)

        del self.state.positions[key]

        self._recompute_total_equity()
        self._save_state()
        return float(pnl)

    def has_position(self, chain: str, symbol: str) -> bool:
        key = f"{chain}:{symbol}"
        return key in self.state.positions

    def get_position(self, chain: str, symbol: str) -> Optional[PositionState]:
        key = f"{chain}:{symbol}"
        return self.state.positions.get(key)

    def open_chains_for_symbol(self, symbol: str) -> list[str]:
        chains = []
        suffix = f":{symbol}"

        for key, pos in self.state.positions.items():
            if key.endswith(suffix):
                chains.append(pos.chain)

        return chains

    # ==========================================================
    # DAILY RESET
    # ==========================================================

    def daily_reset_if_needed(self) -> None:
        today = datetime.utcnow().date().isoformat()
        if self.state.last_reset_day == today:
            return

        self.state.daily_realized_pnl = 0.0
        self.state.last_reset_day = today
        self._save_state()

    # ==========================================================
    # DRAWDOWN
    # ==========================================================

    def current_drawdown(self) -> float:
        if self.state.peak_equity == 0:
            return 0.0

        dd = (self.state.peak_equity - self.state.total_equity) / self.state.peak_equity
        return float(dd)

    # ==========================================================
    # PERSISTENCE
    # ==========================================================

    def _save_state(self) -> None:
        tmp_file = self.state_file + ".tmp"
        with open(tmp_file, "w") as f:
            json.dump(self._serialize(), f, indent=2)
        os.replace(tmp_file, self.state_file)

    def _load_state_with_migration(self) -> PortfolioState:
        """
        Supports:
          - new schema: has "positions"
          - old schema: has "chains" (one position per chain). We migrate realized pnl only.
        """
        with open(self.state_file, "r") as f:
            data = json.load(f)

        # New schema
        if "positions" in data:
            positions = {k: PositionState(**v) for k, v in data.get("positions", {}).items()}
            return PortfolioState(
                total_equity=float(data.get("total_equity", self.initial_equity)),
                peak_equity=float(data.get("peak_equity", self.initial_equity)),
                last_reset_day=data.get("last_reset_day"),
                realized_pnl=float(data.get("realized_pnl", 0.0)),
                daily_realized_pnl=float(data.get("daily_realized_pnl", 0.0)),
                positions=positions,
            )

        # Old schema (migrate realized pnl totals; positions cannot be migrated safely because old
        # chain state does not contain symbol identity)
        if "chains" in data:
            realized_total = 0.0
            daily_total = 0.0
            for _, cs in data.get("chains", {}).items():
                realized_total += float(cs.get("realized_pnl", 0.0))
                daily_total += float(cs.get("daily_realized_pnl", 0.0))

            return PortfolioState(
                total_equity=float(data.get("total_equity", self.initial_equity)),
                peak_equity=float(data.get("peak_equity", self.initial_equity)),
                last_reset_day=data.get("last_reset_day"),
                realized_pnl=realized_total,
                daily_realized_pnl=daily_total,
                positions={},
            )

        # Unknown schema -> reset
        return self._new_state()

    def _serialize(self) -> Dict:
        return {
            "total_equity": self.state.total_equity,
            "peak_equity": self.state.peak_equity,
            "last_reset_day": self.state.last_reset_day,
            "realized_pnl": self.state.realized_pnl,
            "daily_realized_pnl": self.state.daily_realized_pnl,
            "positions": {k: asdict(v) for k, v in self.state.positions.items()},
        }