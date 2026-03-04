class KellyEngine:

    def __init__(self, config):

        self.config = config

        self.trades = []

    def record_trade(self, r_multiple):

        self.trades.append(r_multiple)

        if len(self.trades) > 500:
            self.trades.pop(0)

    def multiplier(self):

        if not self.config["enabled"]:
            return 1.0

        if len(self.trades) < self.config["min_trades"]:
            return 1.0

        wins = [t for t in self.trades if t > 0]
        losses = [t for t in self.trades if t <= 0]

        if not wins or not losses:
            return 1.0

        win_rate = len(wins) / len(self.trades)

        avg_win = sum(wins) / len(wins)

        avg_loss = abs(sum(losses) / len(losses))

        if avg_loss == 0:
            return 1.0

        b = avg_win / avg_loss

        kelly = win_rate - ((1 - win_rate) / b)

        kelly *= self.config["kelly_fraction"]

        kelly = max(self.config["min_mult"], min(self.config["max_mult"], kelly))

        return float(kelly)