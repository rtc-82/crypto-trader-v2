class RiskManager:

    def __init__(
        self,
        max_risk_per_trade,
        max_daily_drawdown_pct,
        risk_reward_ratio,
        atr_stop_multiplier,
        trade_cooldown_seconds,
    ):
        self.max_risk_per_trade = max_risk_per_trade
        self.max_daily_drawdown_pct = max_daily_drawdown_pct
        self.risk_reward_ratio = risk_reward_ratio
        self.atr_stop_multiplier = atr_stop_multiplier
        self.trade_cooldown_seconds = trade_cooldown_seconds

    # ==========================
    # STOP CALCULATION
    # ==========================

    def calculate_stop_distance(self, atr):
        return atr * self.atr_stop_multiplier

    # ==========================
    # TARGET CALCULATION
    # ==========================

    def calculate_targets(self, entry_price, direction, stop_distance):

        if direction == "LONG":
            stop = entry_price - stop_distance
            tp = entry_price + (stop_distance * self.risk_reward_ratio)

        elif direction == "SHORT":
            stop = entry_price + stop_distance
            tp = entry_price - (stop_distance * self.risk_reward_ratio)

        else:
            raise ValueError("Invalid direction")

        return stop, tp