# NOTE: This walk-forward currently validates the *signal/exit engine* via GlobalPerformanceEngine.
# For allocator-level walk-forward (recommended before scaling), segment time ranges,
# rebuild trade streams per segment, and run PortfolioAllocator.simulate per segment.

import pandas as pd

from .strategy_engine import StrategyEngine
from .risk.risk_manager import RiskManager
from .portfolio.position_manager import PositionManager
from .performance.global_performance_engine import GlobalPerformanceEngine
from .config import STRATEGY_CONFIG, ENGINE_CONFIG
from .execution.solana_historical_executor import SolanaHistoricalExecutor


class WalkForwardValidator:

    def __init__(self, df, window_months=6):
        self.df = df.sort_values("timestamp").reset_index(drop=True)
        self.window_months = window_months

    def run(self):

        results = []

        start_date = self.df["timestamp"].min()
        end_date = self.df["timestamp"].max()

        current_start = start_date

        while True:

            train_end = current_start + pd.DateOffset(months=self.window_months)
            test_end = train_end + pd.DateOffset(months=self.window_months)

            if test_end > end_date:
                break

            train_df = self.df[
                (self.df["timestamp"] >= current_start) &
                (self.df["timestamp"] < train_end)
            ]

            test_df = self.df[
                (self.df["timestamp"] >= train_end) &
                (self.df["timestamp"] < test_end)
            ]

            if len(test_df) < 100:
                break

            performance_engine = GlobalPerformanceEngine(starting_equity=100.0)

            self._run_backtest(test_df, performance_engine)

            metrics = performance_engine.simulate_portfolio()

            results.append({
                "train_start": current_start,
                "test_end": test_end,
                "pf": metrics["pf"],
                "expectancy": metrics["expectancy"],
                "trades": metrics["total_trades"]
            })

            current_start += pd.DateOffset(months=self.window_months)

        return results

    def _run_backtest(self, df, performance_engine):

        strategy = StrategyEngine(STRATEGY_CONFIG)

        risk_manager = RiskManager(
            max_risk_per_trade=ENGINE_CONFIG["max_risk_per_trade"],
            max_daily_drawdown_pct=ENGINE_CONFIG["max_daily_drawdown"],
            risk_reward_ratio=ENGINE_CONFIG["risk_reward_ratio"],
            atr_stop_multiplier=ENGINE_CONFIG["atr_stop_multiplier"],
            trade_cooldown_seconds=ENGINE_CONFIG["trade_cooldown"],
        )

        position_manager = PositionManager()
        executor = SolanaHistoricalExecutor(df)

        while executor.has_next():

            candle = executor.get_next_price()
            if candle is None:
                break

            price = candle["close"]
            high = candle["high"]
            low = candle["low"]
            timestamp = candle["timestamp"]

            signal = strategy.generate_signal(
                price=price,
                high=high,
                low=low,
                timestamp=timestamp,
            )

            if signal and not position_manager.has_position():

                stop_distance = risk_manager.calculate_stop_distance(signal.atr)

                stop, tp = risk_manager.calculate_targets(
                    entry_price=price,
                    direction=signal.direction,
                    stop_distance=stop_distance,
                )

                position_manager.open_position(
                    direction=signal.direction,
                    entry_price=price,
                    stop_loss=stop,
                    take_profit=tp,
                )

            if position_manager.has_position():

                exit_trade = position_manager.check_exit(high, low)

                if exit_trade:

                    if exit_trade["result"] == "STOP":
                        r_multiple = -1.0
                    else:
                        r_multiple = ENGINE_CONFIG["risk_reward_ratio"]

                    performance_engine.record_trade(
                        r_multiple,
                        timestamp,
                        "",
                    )