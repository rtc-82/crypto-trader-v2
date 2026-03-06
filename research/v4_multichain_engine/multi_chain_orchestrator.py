# research/v4_multichain_engine/multi_chain_orchestrator.py

from __future__ import annotations
from typing import List, Dict, Tuple
import os
import pickle
import hashlib
import json

from research.v4_multichain_engine.config import STRATEGY_CONFIG, ENGINE_CONFIG, MONTE_CARLO_CONFIG
from research.v4_multichain_engine.portfolio.portfolio_allocator import PortfolioAllocator, Trade
from research.v4_multichain_engine.performance.allocator_monte_carlo import (
    AllocatorMonteCarloEngine,
    MonteCarloConfig,
)

CACHE_DIR = "research/v4_multichain_engine/cache"
os.makedirs(CACHE_DIR, exist_ok=True)


class MultiChainOrchestrator:

    def __init__(self, data_loader):
        self.data_loader = data_loader
        self.starting_equity = float(ENGINE_CONFIG["starting_equity"])

    # ==========================================================
    # CACHE
    # ==========================================================

    def _strategy_hash(self) -> str:
        raw = json.dumps(STRATEGY_CONFIG, sort_keys=True)
        return hashlib.md5(raw.encode()).hexdigest()

    def _cache_path(self) -> str:
        return os.path.join(CACHE_DIR, f"trades_{self._strategy_hash()}.pkl")

    # ==========================================================

    async def run_portfolio(self):

        print("\n========== PORTFOLIO TEST (HYBRID + CORRELATION) ==========\n")

        universe = self.data_loader.load_universe()
        cache_path = self._cache_path()

        if os.path.exists(cache_path):
            print("Loading trade stream from cache...\n")
            with open(cache_path, "rb") as f:
                all_trades, per_asset_stats = pickle.load(f)
        else:
            print("No cache found. Building trade streams...\n")

            all_trades: List[Trade] = []
            per_asset_stats: List[Tuple[str, Dict[str, float]]] = []

            for symbol, df in universe.items():

                if symbol == "BTCUSDT":
                    continue

                tier = self.data_loader.assets.get(symbol, {}).get("tier", "unknown")

                print(f"Building trade stream: {symbol} (tier={tier})")

                trades = await self._extract_trades_for_symbol(symbol, tier, df)

                print(f"  -> trades extracted: {len(trades)}")

                stats = self._compute_trade_stats(trades)
                per_asset_stats.append((symbol, stats))
                all_trades.extend(trades)

            print("\nSaving trade stream cache...\n")
            with open(cache_path, "wb") as f:
                pickle.dump((all_trades, per_asset_stats), f)

        # ==========================================================

        print("\n========== PER-ASSET SUMMARY ==========")

        per_asset_stats.sort(key=lambda x: x[1]["pf"], reverse=True)

        for symbol, s in per_asset_stats:
            print(
                f"{symbol:10s} | trades={int(s['trades']):4d} "
                f"| pf={s['pf']:.3f} | exp={s['expectancy']:.3f}R "
                f"| win={s['win_rate']*100:5.1f}%"
            )

        print("=======================================\n")

        allocator = PortfolioAllocator(
            max_concurrent_positions=ENGINE_CONFIG["max_concurrent_positions"],
            base_risk_pct=ENGINE_CONFIG["portfolio_base_risk_pct"],
            score_lookback_trades=ENGINE_CONFIG["score_lookback_trades"],

            # Back-compat kill switch (phase kill switches passed below)
            drawdown_kill_switch=ENGINE_CONFIG.get("portfolio_kill_switch_dd", 0.25),

            cost_r=ENGINE_CONFIG["cost_r"],
            correlation_threshold=ENGINE_CONFIG.get("correlation_threshold", 0.75),
            data_loader=self.data_loader,
            correlation_lookback_bars=ENGINE_CONFIG.get("correlation_lookback_bars", 200),
            correlation_min_bars=ENGINE_CONFIG.get("correlation_min_bars", 80),

            # Phase switch + ladders
            phase_switch_equity=ENGINE_CONFIG.get("phase_switch_equity", 2000.0),
            acceleration_risk_ladder=ENGINE_CONFIG.get("acceleration_risk_ladder") or ENGINE_CONFIG.get("risk_ladder"),
            preservation_risk_ladder=ENGINE_CONFIG.get("preservation_risk_ladder"),
            acceleration_kill_switch_dd=ENGINE_CONFIG.get("acceleration_kill_switch_dd", 0.35),
            preservation_kill_switch_dd=ENGINE_CONFIG.get("preservation_kill_switch_dd", 0.20),

            # PF throttle per phase
            pf_rolling_window=ENGINE_CONFIG.get("pf_rolling_window", 200),
            pf_pause_below_accel=ENGINE_CONFIG.get("pf_pause_below_accel", 1.05),
            pf_half_risk_below_accel=ENGINE_CONFIG.get("pf_half_risk_below_accel", 1.15),
            pf_resume_above_accel=ENGINE_CONFIG.get("pf_resume_above_accel", 1.20),
            pf_pause_below_preserve=ENGINE_CONFIG.get("pf_pause_below_preserve", 1.10),
            pf_half_risk_below_preserve=ENGINE_CONFIG.get("pf_half_risk_below_preserve", 1.18),
            pf_resume_above_preserve=ENGINE_CONFIG.get("pf_resume_above_preserve", 1.22),

            # Optional slippage model
            slippage_model=ENGINE_CONFIG.get("slippage_model", {"enabled": False}),
        )

        result = allocator.simulate(
            trades=all_trades,
            starting_equity=self.starting_equity,
        )

        print("\n========== PORTFOLIO RESULTS ==========")

        for k, v in result.items():
            if isinstance(v, float):
                if "drawdown" in k:
                    print(f"{k}: {v*100:.2f}%")
                else:
                    print(f"{k}: {v:.4f}")
            else:
                print(f"{k}: {v}")

        print("=======================================\n")

        # ==========================================================
        # MONTE CARLO
        # ==========================================================

        if MONTE_CARLO_CONFIG.get("enabled", False):

            print(">>> ENTERING MONTE CARLO <<<")

            mc_dict = {k: v for k, v in MONTE_CARLO_CONFIG.items() if k != "enabled"}
            mc_cfg = MonteCarloConfig(**mc_dict)

            mc_engine = AllocatorMonteCarloEngine(
                allocator=allocator,
                trades=all_trades,
                starting_equity=self.starting_equity,
                mc_config=mc_cfg,
            )

            mc_results = mc_engine.run()

            print("\n========== MONTE CARLO (ALLOCATOR) ==========")

            for scenario_name, stats in mc_results.items():
                print(f"\n--- Scenario: {scenario_name} ---")
                for k, v in stats.items():
                    if "max_dd" in k or "rate" in k:
                        print(f"{k}: {v*100:.2f}%")
                    else:
                        print(f"{k}: {v:.4f}")

            print("=============================================\n")
