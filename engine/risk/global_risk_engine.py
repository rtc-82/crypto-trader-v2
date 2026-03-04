import time
from dataclasses import dataclass


@dataclass
class RiskConfig:
    max_daily_loss: float
    max_trade_fraction: float
    max_trades_per_hour: int


class GlobalRiskEngine:

    def __init__(self, config: RiskConfig):
        self.config = config
        self.daily_pnl = 0.0
        self.trade_timestamps = []

    def _cleanup_old_trades(self):
        now = time.time()
        one_hour_ago = now - 3600
        self.trade_timestamps = [
            t for t in self.trade_timestamps if t > one_hour_ago
        ]

    def register_trade(self, pnl: float):
        self.daily_pnl += pnl
        self.trade_timestamps.append(time.time())

    def approve_trade(self, wallet_balance: float, trade_size: float) -> bool:

        if self.daily_pnl <= -abs(self.config.max_daily_loss):
            print("🛑 Risk Blocked: Daily loss limit reached.")
            return False

        if trade_size > wallet_balance * self.config.max_trade_fraction:
            print("🛑 Risk Blocked: Trade too large.")
            return False

        self._cleanup_old_trades()
        if len(self.trade_timestamps) >= self.config.max_trades_per_hour:
            print("🛑 Risk Blocked: Too many trades this hour.")
            return False

        return True