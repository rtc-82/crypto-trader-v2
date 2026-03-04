from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import numpy as np

from research.v4_multichain_engine.portfolio.portfolio_allocator import (
    PortfolioAllocator,
    Trade,
)


@dataclass(frozen=True)
class MonteCarloConfig:
    simulations: int = 1000
    seed: int = 42

    run_baseline: bool = True
    run_cost_2x: bool = True
    run_loss_clustering: bool = True

    # Optional: slippage stress test (adds additional stochastic R friction per trade)
    run_slippage: bool = False
    slippage_mean_r: float = 0.00
    slippage_std_r: float = 0.01

    block_min: int = 10
    block_max: int = 30

    dd_fail_level: float = 0.25
    pf_fail_level: float = 1.00


class AllocatorMonteCarloEngine:

    def __init__(
        self,
        allocator: PortfolioAllocator,
        trades: List[Trade],
        starting_equity: float,
        mc_config: MonteCarloConfig,
    ):
        self.allocator = allocator
        self.trades = list(trades)
        self.starting_equity = float(starting_equity)
        self.cfg = mc_config

        self._rng = np.random.default_rng(self.cfg.seed)

        self._r_pool = np.array([float(t.r) for t in self.trades], dtype=float)
        if self._r_pool.size == 0:
            raise ValueError("No trades provided for Monte Carlo.")

    # ==========================================================

    def run(self) -> Dict[str, Dict[str, float]]:
        results: Dict[str, Dict[str, float]] = {}

        if self.cfg.run_baseline:
            results["baseline"] = self._run_scenario_iid(cost_override=None, slippage_override=None)

        if self.cfg.run_cost_2x:
            results["cost_2x"] = self._run_scenario_iid(
                cost_override=self.allocator.cost_r * 2.0,
                slippage_override=None,
            )

        if self.cfg.run_loss_clustering:
            results["loss_cluster"] = self._run_scenario_block_bootstrap(
                cost_override=None,
                slippage_override=None,
            )

        if self.cfg.run_slippage:
            results["slippage"] = self._run_scenario_iid(
                cost_override=None,
                slippage_override={
                    "enabled": True,
                    "mean_r": float(self.cfg.slippage_mean_r),
                    "std_r": float(self.cfg.slippage_std_r),
                    "seed": int(self.cfg.seed),
                    "clip_min_r": 0.0,
                },
            )

        return results

    # ==========================================================

    def _run_scenario_iid(self, cost_override: Optional[float], slippage_override: Optional[dict]) -> Dict[str, float]:
        finals, dds, pfs = self._simulate_many(
            sampler=self._sample_r_iid,
            cost_override=cost_override,
            slippage_override=slippage_override,
        )
        return self._summarize(finals, dds, pfs)

    def _run_scenario_block_bootstrap(
        self,
        cost_override: Optional[float],
        slippage_override: Optional[dict],
    ) -> Dict[str, float]:
        finals, dds, pfs = self._simulate_many(
            sampler=self._sample_r_block_bootstrap,
            cost_override=cost_override,
            slippage_override=slippage_override,
        )
        return self._summarize(finals, dds, pfs)

    # ==========================================================

    def _simulate_many(
        self,
        sampler,
        cost_override: Optional[float],
        slippage_override: Optional[dict],
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:

        n = len(self.trades)

        finals = np.zeros(self.cfg.simulations, dtype=float)
        dds = np.zeros(self.cfg.simulations, dtype=float)
        pfs = np.zeros(self.cfg.simulations, dtype=float)

        for i in range(self.cfg.simulations):

            if i % 100 == 0:
                print(f"Monte Carlo progress: {i}/{self.cfg.simulations}")

            r_series = sampler(n)

            trades_variant = [
                Trade(
                    entry_ts=t.entry_ts,
                    exit_ts=t.exit_ts,
                    r=float(r),
                    symbol=t.symbol,
                    tier=t.tier,
                )
                for t, r in zip(self.trades, r_series)
            ]

            allocator_variant = PortfolioAllocator(
                max_concurrent_positions=self.allocator.max_concurrent_positions,
                base_risk_pct=self.allocator.base_risk_pct,
                score_lookback_trades=self.allocator.score_lookback_trades,
                drawdown_kill_switch=self.allocator.drawdown_kill_switch,
                cost_r=float(cost_override) if cost_override is not None else self.allocator.cost_r,
                correlation_threshold=self.allocator.correlation_threshold,
                data_loader=self.allocator.data_loader,
                correlation_lookback_bars=self.allocator.correlation_lookback_bars,
                correlation_min_bars=self.allocator.correlation_min_bars,

                phase_switch_equity=self.allocator.phase_switch_equity,
                acceleration_risk_ladder=self.allocator.acceleration_risk_ladder,
                preservation_risk_ladder=self.allocator.preservation_risk_ladder,
                acceleration_kill_switch_dd=self.allocator.acceleration_kill_switch_dd,
                preservation_kill_switch_dd=self.allocator.preservation_kill_switch_dd,

                pf_pause_below_accel=self.allocator.pf_pause_below_accel,
                pf_half_risk_below_accel=self.allocator.pf_half_risk_below_accel,
                pf_resume_above_accel=self.allocator.pf_resume_above_accel,
                pf_pause_below_preserve=self.allocator.pf_pause_below_preserve,
                pf_half_risk_below_preserve=self.allocator.pf_half_risk_below_preserve,
                pf_resume_above_preserve=self.allocator.pf_resume_above_preserve,
                pf_rolling_window=self.allocator.pf_rolling_window,

                slippage_model=slippage_override if slippage_override is not None else self.allocator.slippage_model,
            )

            out = allocator_variant.simulate(
                trades=trades_variant,
                starting_equity=self.starting_equity,
            )

            finals[i] = float(out["final_equity"])
            dds[i] = float(out["max_drawdown"])
            pfs[i] = float(out["pf"])

        return finals, dds, pfs

    # ==========================================================

    def _sample_r_iid(self, n: int) -> np.ndarray:
        idx = self._rng.integers(0, self._r_pool.size, size=n)
        return self._r_pool[idx]

    def _sample_r_block_bootstrap(self, n: int) -> np.ndarray:
        out: List[float] = []
        while len(out) < n:
            block_len = int(self._rng.integers(self.cfg.block_min, self.cfg.block_max + 1))
            start = int(self._rng.integers(0, max(1, self._r_pool.size - block_len + 1)))
            block = self._r_pool[start : start + block_len]
            out.extend(block.tolist())
        return np.array(out[:n], dtype=float)

    # ==========================================================

    def _summarize(
        self,
        finals: np.ndarray,
        dds: np.ndarray,
        pfs: np.ndarray,
    ) -> Dict[str, float]:

        def pct(x: np.ndarray, q: float) -> float:
            return float(np.percentile(x, q))

        pf_fail = float(np.mean(pfs < self.cfg.pf_fail_level))
        dd_fail = float(np.mean(dds > self.cfg.dd_fail_level))

        return {
            "simulations": float(self.cfg.simulations),

            "final_equity_median": pct(finals, 50),
            "final_equity_p05": pct(finals, 5),
            "final_equity_p95": pct(finals, 95),
            "final_equity_worst": float(np.min(finals)),

            "max_dd_median": pct(dds, 50),
            "max_dd_p95": pct(dds, 95),
            "max_dd_worst": float(np.max(dds)),

            "pf_median": pct(pfs, 50),
            "pf_p05": pct(pfs, 5),

            "pf_fail_rate": pf_fail,
            "dd_fail_rate": dd_fail,
        }
