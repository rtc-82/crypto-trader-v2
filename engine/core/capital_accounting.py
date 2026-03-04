from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, Optional
import json
import os
from datetime import datetime


# ==========================================================
# STATE MODELS
# ==========================================================

@dataclass
class ChainState:
    position: Optional[str] = None
    entry_price: Optional[float] = None
    position_size: Optional[float] = None
    realized_pnl: float = 0.0
    daily_realized_pnl: float = 0.0


@dataclass
class PortfolioState:
    total_equity: float
    peak_equity: float
    last_reset_day: Optional[str]
    chains: Dict[str, ChainState]


# ==========================================================
# CAPITAL ACCOUNTING ENGINE
# ==========================================================

class CapitalAccounting:

    def __init__(
        self,
        initial_equity: float,
        chains: list[str],
        state_file: str = "engine_state.json",
    ):
        self.state_file = state_file

        if os.path.exists(self.state_file):
            self.state = self._load_state()
        else:
            self.state = PortfolioState(
                total_equity=float(initial_equity),
                peak_equity=float(initial_equity),
                last_reset_day=None,
                chains={chain: ChainState() for chain in chains},
            )
            self._save_state()

    # ==========================================================
    # EQUITY MANAGEMENT
    # ==========================================================

    def update_realized_pnl(self, chain: str, pnl: float) -> None:

        chain_state = self.state.chains[chain]

        chain_state.realized_pnl += pnl
        chain_state.daily_realized_pnl += pnl

        self.state.total_equity += pnl

        if self.state.total_equity > self.state.peak_equity:
            self.state.peak_equity = self.state.total_equity

        self._save_state()

    # ==========================================================
    # POSITION TRACKING
    # ==========================================================

    def open_position(
        self,
        chain: str,
        direction: str,
        entry_price: float,
        size: float,
    ) -> None:

        chain_state = self.state.chains[chain]

        chain_state.position = direction
        chain_state.entry_price = float(entry_price)
        chain_state.position_size = float(size)

        self._save_state()

    def close_position(self, chain: str) -> None:

        chain_state = self.state.chains[chain]

        chain_state.position = None
        chain_state.entry_price = None
        chain_state.position_size = None

        self._save_state()

    # ==========================================================
    # DAILY RESET
    # ==========================================================

    def daily_reset_if_needed(self) -> None:

        today = datetime.utcnow().date().isoformat()

        if self.state.last_reset_day == today:
            return

        for chain_state in self.state.chains.values():
            chain_state.daily_realized_pnl = 0.0

        self.state.last_reset_day = today
        self._save_state()

    # ==========================================================
    # DRAWDOWN
    # ==========================================================

    def current_drawdown(self) -> float:

        if self.state.peak_equity == 0:
            return 0.0

        dd = (
            self.state.peak_equity - self.state.total_equity
        ) / self.state.peak_equity

        return float(dd)

    # ==========================================================
    # PERSISTENCE
    # ==========================================================

    def _save_state(self) -> None:

        tmp_file = self.state_file + ".tmp"

        with open(tmp_file, "w") as f:
            json.dump(self._serialize(), f, indent=2)

        os.replace(tmp_file, self.state_file)

    def _load_state(self) -> PortfolioState:

        with open(self.state_file, "r") as f:
            data = json.load(f)

        chains = {
            name: ChainState(**state)
            for name, state in data["chains"].items()
        }

        return PortfolioState(
            total_equity=data["total_equity"],
            peak_equity=data["peak_equity"],
            last_reset_day=data["last_reset_day"],
            chains=chains,
        )

    def _serialize(self) -> Dict:

        return {
            "total_equity": self.state.total_equity,
            "peak_equity": self.state.peak_equity,
            "last_reset_day": self.state.last_reset_day,
            "chains": {
                name: asdict(state)
                for name, state in self.state.chains.items()
            },
        }