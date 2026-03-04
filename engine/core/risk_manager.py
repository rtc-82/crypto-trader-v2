class RiskManager:
    """
    Position sizing based on ATR risk.

    position_size = risk_dollars / stop_distance
    """

    def __init__(self, config):

        self.risk_per_trade = config.get("risk_per_trade", 0.01)
        self.max_position_size = config.get("max_position_size", 0.25)

    def calculate_position_size(self, equity, price, atr):

        if atr <= 0 or price <= 0 or equity <= 0:
            return 0.0

        # risk capital per trade
        risk_dollars = equity * self.risk_per_trade

        # stop distance based on ATR
        stop_distance = atr

        size = risk_dollars / stop_distance

        # position cap
        max_size = (equity * self.max_position_size) / price

        size = min(size, max_size)

        return float(size)