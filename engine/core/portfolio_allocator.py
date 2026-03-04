from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple, Optional, Any
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Trade:
    entry_ts: object
    exit_ts: object
    r: float
    symbol: str
    tier: str = "unknown"


@dataclass
class _OpenPosition:
    symbol: str
    exit_ts: pd.Timestamp
    r_adj: float
    risk_dollars: float
    entry_ts: pd.Timestamp


class PortfolioAllocator:

    """
    Research portfolio allocator used for:

    - walk forward testing
    - monte carlo
    - risk ladder validation
    - correlation modelling

    Compatible with ENGINE_CONFIG.
    """

    def __init__(self, config: Dict, data_loader):

        self.config = config

        # ---------------------------------------
        # BASIC SETTINGS
        # ---------------------------------------

        self.max_concurrent_positions = config.get("max_concurrent_positions", 1)
        self.base_risk_pct = config.get("portfolio_base_risk_pct", 0.01)
        self.score_lookback_trades = config.get("score_lookback_trades", 120)

        self.cost_r = config.get("cost_r", 0.0)

        # ---------------------------------------
        # CORRELATION
        # ---------------------------------------

        self.correlation_threshold = config.get("correlation_threshold", 0.75)
        self.correlation_lookback_bars = config.get("correlation_lookback_bars", 200)
        self.correlation_min_bars = config.get("correlation_min_bars", 80)

        # ---------------------------------------
        # PHASE SWITCHING
        # ---------------------------------------

        self.phase_switch_equity = config.get("phase_switch_equity", 2000)

        self.acceleration_risk_ladder = config.get(
            "acceleration_risk_ladder",
            [(250, 0.02), (750, 0.0175), (1500, 0.015), (3000, 0.0125), (float("inf"), 0.01)],
        )

        self.preservation_risk_ladder = config.get(
            "preservation_risk_ladder",
            [(2500, 0.0125), (5000, 0.01), (10000, 0.008), (float("inf"), 0.007)],
        )

        self.acceleration_kill_switch_dd = config.get("acceleration_kill_switch_dd", 0.35)
        self.preservation_kill_switch_dd = config.get("preservation_kill_switch_dd", 0.20)

        # ---------------------------------------
        # PF THROTTLE
        # ---------------------------------------

        self.pf_pause_below_accel = config.get("pf_pause_below_accel", 1.05)
        self.pf_half_risk_below_accel = config.get("pf_half_risk_below_accel", 1.15)
        self.pf_resume_above_accel = config.get("pf_resume_above_accel", 1.20)

        self.pf_pause_below_preserve = config.get("pf_pause_below_preserve", 1.10)
        self.pf_half_risk_below_preserve = config.get("pf_half_risk_below_preserve", 1.18)
        self.pf_resume_above_preserve = config.get("pf_resume_above_preserve", 1.22)

        self.pf_rolling_window = config.get("pf_rolling_window", 200)

        # ---------------------------------------
        # SLIPPAGE MODEL
        # ---------------------------------------

        self.slippage_model = config.get("slippage_model", {"enabled": False})

        self._slip_rng = None

        if self.slippage_model.get("enabled", False):

            seed = self.slippage_model.get("seed", 42)

            self._slip_rng = np.random.default_rng(seed)

        # ---------------------------------------
        # DATA LOADER
        # ---------------------------------------

        self.data_loader = data_loader

        self._universe = self.data_loader.load_universe()

        self._returns: Dict[str, pd.Series] = {}

        for symbol, df in self._universe.items():

            s = df[["timestamp", "close"]].copy()

            s["timestamp"] = pd.to_datetime(s["timestamp"], utc=True)

            s = s.sort_values("timestamp").set_index("timestamp")

            self._returns[symbol] = s["close"].pct_change()

    # ----------------------------------------------------
    # RISK LADDER
    # ----------------------------------------------------

    def _ladder_risk_pct(self, equity, ladder):

        for level, pct in ladder:

            if equity < level:

                return pct

        return ladder[-1][1]

    # ----------------------------------------------------
    # CORRELATION
    # ----------------------------------------------------

    def _returns_asof(self, symbol, ts):

        r = self._returns.get(symbol)

        if r is None:

            return None

        sliced = r.loc[:ts].dropna()

        if len(sliced) < self.correlation_min_bars:

            return None

        return sliced.tail(self.correlation_lookback_bars)

    def _is_correlated(self, symbol, entry_ts, open_symbols):

        cand = self._returns_asof(symbol, entry_ts)

        if cand is None:

            return False

        for sym in open_symbols:

            other = self._returns_asof(sym, entry_ts)

            if other is None:

                continue

            joined = pd.concat([cand, other], axis=1).dropna()

            if len(joined) < self.correlation_min_bars:

                continue

            corr = joined.iloc[:, 0].corr(joined.iloc[:, 1])

            if abs(corr) >= self.correlation_threshold:

                return True

        return False

    # ----------------------------------------------------
    # SLIPPAGE
    # ----------------------------------------------------

    def _sample_slippage_r(self):

        if not self.slippage_model.get("enabled", False):

            return 0.0

        mu = self.slippage_model.get("mean_r", 0.0)
        sd = self.slippage_model.get("std_r", 0.0)
        clip_min = self.slippage_model.get("clip_min_r", 0.0)

        x = self._slip_rng.normal(mu, sd) if sd > 0 else mu

        return max(clip_min, x)

    # ----------------------------------------------------
    # SIMULATION
    # ----------------------------------------------------

    def simulate(self, trades: List[Trade], starting_equity: float):

        trades_sorted = sorted(trades, key=lambda t: t.entry_ts)

        equity = float(starting_equity)

        peak = equity

        max_dd = 0.0

        accepted_rs = []

        skipped = 0

        phase = "accel"

        ladder = self.acceleration_risk_ladder

        for trade in trades_sorted:

            entry_ts = pd.to_datetime(trade.entry_ts, utc=True)

            exit_ts = pd.to_datetime(trade.exit_ts, utc=True)

            if equity >= self.phase_switch_equity and phase == "accel":

                phase = "preserve"

                ladder = self.preservation_risk_ladder

            slip = self._sample_slippage_r()

            r_adj = trade.r - self.cost_r - slip

            risk_pct = self._ladder_risk_pct(equity, ladder)

            risk_dollars = equity * risk_pct

            pnl = risk_dollars * r_adj

            equity += pnl

            accepted_rs.append(r_adj)

            peak = max(peak, equity)

            dd = (peak - equity) / peak

            max_dd = max(max_dd, dd)

        gp = sum(r for r in accepted_rs if r > 0)
        gl = sum(-r for r in accepted_rs if r < 0)

        pf = gp / gl if gl > 0 else 0

        expectancy = sum(accepted_rs) / len(accepted_rs) if accepted_rs else 0

        return {
            "final_equity": equity,
            "pf": pf,
            "expectancy": expectancy,
            "max_drawdown": max_dd,
            "accepted_trades": len(accepted_rs),
            "skipped_trades": skipped,
            "phase_end": phase,
        }