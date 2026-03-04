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
    """Shared-capital portfolio allocator (allocator = the system).

    Core features:
    - Max concurrency
    - Cost model (R-adjust)
    - Optional stochastic slippage model (R-adjust)
    - Correlation gating (no lookahead)
    - Rolling PF throttle (phase-aware)
    - Equity-based risk ladders (phase-aware)
    - Hard phase switch at target equity (locks into preservation)
    - "Never increase risk after reduction" enforcement (even if equity drops)
    - Drawdown kill switch (phase-aware)
    """

    def __init__(
        self,
        max_concurrent_positions: int,
        base_risk_pct: float,
        score_lookback_trades: int,
        drawdown_kill_switch: float,
        cost_r: float,
        correlation_threshold: float,
        data_loader,
        correlation_lookback_bars: int = 200,
        correlation_min_bars: int = 80,

        # ---- Risk ladders / phase switching ----
        phase_switch_equity: float = 2000.0,
        acceleration_risk_ladder: Optional[Sequence[Tuple[float, float]]] = None,
        preservation_risk_ladder: Optional[Sequence[Tuple[float, float]]] = None,
        acceleration_kill_switch_dd: float = 0.35,
        preservation_kill_switch_dd: float = 0.20,

        # ---- PF throttle per phase ----
        pf_pause_below_accel: float = 1.05,
        pf_half_risk_below_accel: float = 1.15,
        pf_resume_above_accel: float = 1.20,
        pf_pause_below_preserve: float = 1.10,
        pf_half_risk_below_preserve: float = 1.18,
        pf_resume_above_preserve: float = 1.22,
        pf_rolling_window: int = 200,

        # Optional: stochastic slippage model (extra R deducted per trade)
        slippage_model: Optional[Dict[str, Any]] = None,
    ):
        self.max_concurrent_positions = int(max_concurrent_positions)
        self.base_risk_pct = float(base_risk_pct)
        self.score_lookback_trades = int(score_lookback_trades)

        # Cost / friction
        self.cost_r = float(cost_r)

        # Correlation
        self.correlation_threshold = float(correlation_threshold)
        self.correlation_lookback_bars = int(correlation_lookback_bars)
        self.correlation_min_bars = int(correlation_min_bars)

        # Phase switching
        self.phase_switch_equity = float(phase_switch_equity)
        self.acceleration_kill_switch_dd = float(acceleration_kill_switch_dd)
        self.preservation_kill_switch_dd = float(preservation_kill_switch_dd)

        # Ladders
        self.acceleration_risk_ladder: List[Tuple[float, float]] = (
            list(acceleration_risk_ladder) if acceleration_risk_ladder else [
                (250, 0.0200),
                (750, 0.0175),
                (1500, 0.0150),
                (3000, 0.0125),
                (float("inf"), 0.0100),
            ]
        )
        self.preservation_risk_ladder: List[Tuple[float, float]] = (
            list(preservation_risk_ladder) if preservation_risk_ladder else [
                (2500, 0.0125),
                (5000, 0.0100),
                (10000, 0.0080),
                (float("inf"), 0.0070),
            ]
        )

        # Back-compat default kill switch (used only if you bypass phase configs)
        self.drawdown_kill_switch = float(drawdown_kill_switch)

        # PF throttle per phase
        self.pf_pause_below_accel = float(pf_pause_below_accel)
        self.pf_half_risk_below_accel = float(pf_half_risk_below_accel)
        self.pf_resume_above_accel = float(pf_resume_above_accel)

        self.pf_pause_below_preserve = float(pf_pause_below_preserve)
        self.pf_half_risk_below_preserve = float(pf_half_risk_below_preserve)
        self.pf_resume_above_preserve = float(pf_resume_above_preserve)

        self.pf_rolling_window = int(pf_rolling_window)

        # Slippage model
        self.slippage_model = slippage_model or {"enabled": False}
        self._slip_rng = None
        if bool(self.slippage_model.get("enabled", False)):
            seed = int(self.slippage_model.get("seed", 42))
            self._slip_rng = np.random.default_rng(seed)

        # Data
        self.data_loader = data_loader
        self._universe = self.data_loader.load_universe()

        # Precompute returns series for correlation gating (time-correct)
        self._returns: Dict[str, pd.Series] = {}
        for symbol, df in self._universe.items():
            s = df[["timestamp", "close"]].copy()
            s["timestamp"] = pd.to_datetime(s["timestamp"], utc=True)
            s = s.sort_values("timestamp").set_index("timestamp")
            self._returns[symbol] = s["close"].pct_change()

    # ==========================================================
    # LADDERS
    # ==========================================================

    @staticmethod
    def _ladder_risk_pct(equity: float, ladder: Sequence[Tuple[float, float]]) -> float:
        e = float(equity)
        for upper, pct in ladder:
            if e < float(upper):
                return float(pct)
        return float(ladder[-1][1])

    def _phase_params(self, phase: str) -> Dict[str, float]:
        if phase == "preserve":
            return {
                "pf_pause_below": self.pf_pause_below_preserve,
                "pf_half_risk_below": self.pf_half_risk_below_preserve,
                "pf_resume_above": self.pf_resume_above_preserve,
                "kill_switch_dd": self.preservation_kill_switch_dd,
            }
        return {
            "pf_pause_below": self.pf_pause_below_accel,
            "pf_half_risk_below": self.pf_half_risk_below_accel,
            "pf_resume_above": self.pf_resume_above_accel,
            "kill_switch_dd": self.acceleration_kill_switch_dd,
        }

    # ==========================================================
    # CORRELATION (no lookahead)
    # ==========================================================

    def _returns_asof(self, symbol: str, ts: pd.Timestamp):
        r = self._returns.get(symbol)
        if r is None:
            return None
        sliced = r.loc[:ts].dropna()
        if len(sliced) < self.correlation_min_bars:
            return None
        return sliced.tail(self.correlation_lookback_bars)

    def _is_correlated(self, symbol: str, entry_ts: pd.Timestamp, open_symbols: List[str]) -> bool:
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

    # ==========================================================
    # FRICTION
    # ==========================================================

    def _sample_slippage_r(self) -> float:
        if not bool(self.slippage_model.get("enabled", False)):
            return 0.0
        if self._slip_rng is None:
            self._slip_rng = np.random.default_rng(int(self.slippage_model.get("seed", 42)))
        mu = float(self.slippage_model.get("mean_r", 0.0))
        sd = float(self.slippage_model.get("std_r", 0.0))
        clip_min = float(self.slippage_model.get("clip_min_r", 0.0))
        x = float(self._slip_rng.normal(mu, sd)) if sd > 0 else mu
        return max(clip_min, x)

    # ==========================================================
    # SIMULATION
    # ==========================================================

    def simulate(
        self,
        trades: List[Trade],
        starting_equity: float,
        rolling_pf_window: Optional[int] = None,
    ):
        trades_sorted = sorted(trades, key=lambda t: t.entry_ts)

        equity = float(starting_equity)
        peak = equity
        max_dd = 0.0

        accepted_rs: List[float] = []
        open_positions: List[_OpenPosition] = []

        skipped = 0
        risk_multiplier = 1.0
        paused = False

        phase = "accel"
        phase_locked = False

        pf_window = int(rolling_pf_window) if rolling_pf_window is not None else self.pf_rolling_window

        # ceiling enforces "never increase after reduction"
        ladder_now = self.acceleration_risk_ladder
        risk_ceiling_pct = self._ladder_risk_pct(equity, ladder_now)

        def rolling_pf(rs: List[float]) -> float:
            if len(rs) < pf_window:
                return 999.0
            window = rs[-pf_window:]
            gp = sum(r for r in window if r > 0)
            gl = sum(-r for r in window if r < 0)
            if gl == 0:
                return 999.0 if gp > 0 else 0.0
            return gp / gl

        def update_phase_if_needed():
            nonlocal phase, phase_locked, ladder_now, risk_ceiling_pct
            if phase_locked:
                return
            if equity >= self.phase_switch_equity:
                phase = "preserve"
                phase_locked = True
                ladder_now = self.preservation_risk_ladder
                # reset ceiling to current ladder pct (still can't increase later)
                risk_ceiling_pct = min(risk_ceiling_pct, self._ladder_risk_pct(equity, ladder_now))

        def close_positions(cutoff_ts: pd.Timestamp):
            nonlocal equity, peak, max_dd, open_positions, accepted_rs, risk_ceiling_pct

            still_open: List[_OpenPosition] = []
            for pos in open_positions:
                if pos.exit_ts <= cutoff_ts:
                    pnl = pos.risk_dollars * pos.r_adj
                    equity += pnl
                    accepted_rs.append(pos.r_adj)

                    peak = max(peak, equity)
                    dd = (peak - equity) / peak if peak > 0 else 0.0
                    max_dd = max(max_dd, dd)

                    update_phase_if_needed()

                    # update ceiling only downward (never allow increases)
                    risk_ceiling_pct = min(risk_ceiling_pct, self._ladder_risk_pct(equity, ladder_now))
                else:
                    still_open.append(pos)

            open_positions = still_open

        # ------------------------------------------------------

        kill_reason = None
        kill_ts = None

        for trade in trades_sorted:
            entry_ts = pd.to_datetime(trade.entry_ts, utc=True)
            exit_ts = pd.to_datetime(trade.exit_ts, utc=True)

            close_positions(entry_ts)

            # phase might flip after closing positions
            update_phase_if_needed()
            params = self._phase_params("preserve" if phase == "preserve" else "accel")
            kill_switch = float(params["kill_switch_dd"])

            # Kill-switch check (stop taking new risk; close remaining naturally)
            if max_dd >= kill_switch:
                kill_reason = f"drawdown_kill_switch_hit_{phase}"
                kill_ts = entry_ts
                break

            current_pf = rolling_pf(accepted_rs)

            # PF throttle (phase-aware)
            if not paused:
                if current_pf < params["pf_pause_below"]:
                    paused = True
                elif current_pf < params["pf_half_risk_below"]:
                    risk_multiplier = 0.5
                else:
                    risk_multiplier = 1.0
            else:
                if current_pf > params["pf_resume_above"]:
                    paused = False
                    risk_multiplier = 1.0

            if paused:
                skipped += 1
                continue

            if len(open_positions) >= self.max_concurrent_positions:
                skipped += 1
                continue

            if self._is_correlated(trade.symbol, entry_ts, [p.symbol for p in open_positions]):
                skipped += 1
                continue

            # cost + (optional) slippage adjusted R
            slip_r = self._sample_slippage_r()
            r_adj = float(trade.r) - self.cost_r - slip_r

            # ladder risk + ceiling + throttle multiplier
            ladder_pct = self._ladder_risk_pct(equity, ladder_now)
            risk_ceiling_pct = min(risk_ceiling_pct, ladder_pct)  # ceiling never increases
            final_risk_pct = risk_ceiling_pct * risk_multiplier
            risk_dollars = equity * final_risk_pct

            open_positions.append(
                _OpenPosition(
                    symbol=trade.symbol,
                    exit_ts=exit_ts,
                    r_adj=r_adj,
                    risk_dollars=risk_dollars,
                    entry_ts=entry_ts,
                )
            )

        # Close remaining (even if killed)
        for pos in sorted(open_positions, key=lambda p: p.exit_ts):
            pnl = pos.risk_dollars * pos.r_adj
            equity += pnl
            accepted_rs.append(pos.r_adj)

            peak = max(peak, equity)
            dd = (peak - equity) / peak if peak > 0 else 0.0
            max_dd = max(max_dd, dd)

            update_phase_if_needed()
            risk_ceiling_pct = min(risk_ceiling_pct, self._ladder_risk_pct(equity, ladder_now))

        gp = sum(r for r in accepted_rs if r > 0)
        gl = sum(-r for r in accepted_rs if r < 0)
        pf = gp / gl if gl > 0 else 0.0
        expectancy = (sum(accepted_rs) / len(accepted_rs)) if accepted_rs else 0.0

        return {
            "starting_equity": float(starting_equity),
            "final_equity": float(equity),
            "pf": float(pf),
            "expectancy": float(expectancy),
            "max_drawdown": float(max_dd),
            "accepted_trades": int(len(accepted_rs)),
            "skipped_trades": int(skipped),
            "phase_end": str(phase),
            "phase_locked": bool(phase_locked),
            "killed": bool(kill_reason is not None),
            "kill_reason": kill_reason,
            "kill_ts": kill_ts,
        }
