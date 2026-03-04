# research/v4_multichain_engine/performance/global_performance_engine.py

from __future__ import annotations

from datetime import timedelta
import random
from typing import Dict, List


class GlobalPerformanceEngine:
    """
    Portfolio-level performance engine (standalone).

    Note:
    The "real" portfolio shared-capital + concurrency model is now implemented
    in PortfolioAllocator. This class remains useful for:
    - single-stream trade simulations
    - diagnostics
    - Monte Carlo
    """

    def __init__(self, starting_equity: float = 100.0):
        self.starting_equity = float(starting_equity)
        self.trades: List[Dict] = []

    def record_trade(self, r_multiple, timestamp, symbol):
        self.trades.append({
            "r": float(r_multiple),
            "timestamp": timestamp,
            "symbol": symbol
        })

    def simulate_portfolio(self) -> Dict[str, object]:
        if not self.trades:
            return self._empty_metrics()

        sorted_trades = sorted(self.trades, key=lambda x: x["timestamp"])

        equity = self.starting_equity
        peak = equity
        max_dd = 0.0

        wins = 0
        losses = 0
        total_r = 0.0

        equity_curve = [equity]

        for trade in sorted_trades:
            r = float(trade["r"])
            equity *= (1.0 + r * 0.01)  # legacy 1% per trade stream sim

            peak = max(peak, equity)
            dd = (peak - equity) / peak if peak > 0 else 0.0
            max_dd = max(max_dd, dd)

            equity_curve.append(equity)

            total_r += r
            if r > 0:
                wins += 1
            elif r < 0:
                losses += 1

        total_trades = wins + losses
        pf = self._profit_factor(sorted_trades)
        expectancy = total_r / total_trades if total_trades > 0 else 0.0

        return {
            "total_trades": total_trades,
            "pf": pf,
            "expectancy": expectancy,
            "final_equity": equity,
            "max_drawdown": max_dd,
            "equity_curve_points": len(equity_curve),
        }

    def _profit_factor(self, trades):
        gross_profit = 0.0
        gross_loss = 0.0

        for t in trades:
            r = float(t["r"])
            if r > 0:
                gross_profit += r
            elif r < 0:
                gross_loss += abs(r)

        if gross_loss == 0:
            return float("inf") if gross_profit > 0 else 0.0

        return gross_profit / gross_loss

    def rolling_metrics(self, days):
        if not self.trades:
            return {"rolling_pf": 0.0, "rolling_expectancy": 0.0, "rolling_trades": 0}

        sorted_trades = sorted(self.trades, key=lambda x: x["timestamp"])
        last_ts = sorted_trades[-1]["timestamp"]
        cutoff = last_ts - timedelta(days=days)

        filtered = [t for t in sorted_trades if t["timestamp"] >= cutoff]
        if not filtered:
            return {"rolling_pf": 0.0, "rolling_expectancy": 0.0, "rolling_trades": 0}

        gross_profit = sum(t["r"] for t in filtered if t["r"] > 0)
        gross_loss = sum(abs(t["r"]) for t in filtered if t["r"] < 0)
        pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")
        expectancy = sum(t["r"] for t in filtered) / len(filtered)

        return {"rolling_pf": pf, "rolling_expectancy": expectancy, "rolling_trades": len(filtered)}

    def run_monte_carlo(self, simulations=1000):
        if not self.trades:
            print("No trades to simulate.")
            return

        final_equities = []
        max_drawdowns = []

        for _ in range(simulations):
            shuffled = self.trades.copy()
            random.shuffle(shuffled)

            equity = self.starting_equity
            peak = equity
            max_dd = 0.0

            for trade in shuffled:
                r = float(trade["r"])
                equity *= (1.0 + r * 0.01)

                peak = max(peak, equity)
                dd = (peak - equity) / peak if peak > 0 else 0.0
                max_dd = max(max_dd, dd)

            final_equities.append(equity)
            max_drawdowns.append(max_dd)

        final_equities.sort()
        max_drawdowns.sort()

        print("\n========== MONTE CARLO RESULTS ==========")
        print(f"Simulations: {simulations}")
        print(f"Median Final Equity: {final_equities[len(final_equities)//2]:.2f}")
        print(f"Worst Final Equity: {final_equities[0]:.2f}")
        print(f"Best Final Equity: {final_equities[-1]:.2f}")
        print(f"Median Max Drawdown: {max_drawdowns[len(max_drawdowns)//2]*100:.2f}%")
        print(f"Worst Max Drawdown: {max_drawdowns[-1]*100:.2f}%")
        print("==========================================\n")

    def _empty_metrics(self):
        return {
            "total_trades": 0,
            "pf": 0.0,
            "expectancy": 0.0,
            "final_equity": self.starting_equity,
            "max_drawdown": 0.0,
            "equity_curve_points": 1,
        }