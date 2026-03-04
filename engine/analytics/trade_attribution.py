class TradeAttribution:

    def __init__(self):

        self.by_symbol = {}
        self.by_regime = {}

    def record(self, symbol, regime, r):

        # symbol attribution
        if symbol not in self.by_symbol:
            self.by_symbol[symbol] = []

        self.by_symbol[symbol].append(r)

        # regime attribution
        if regime not in self.by_regime:
            self.by_regime[regime] = []

        self.by_regime[regime].append(r)

    def summary(self):

        def stats(trades):

            if not trades:
                return {}

            wins = [t for t in trades if t > 0]
            losses = [t for t in trades if t <= 0]

            win_rate = len(wins) / len(trades)

            gross_profit = sum(wins)
            gross_loss = abs(sum(losses))

            pf = gross_profit / gross_loss if gross_loss else 0

            avg_r = sum(trades) / len(trades)

            return {
                "trades": len(trades),
                "win_rate": round(win_rate, 2),
                "profit_factor": round(pf, 2),
                "avg_r": round(avg_r, 3)
            }

        result = {
            "symbol": {},
            "regime": {}
        }

        for k, v in self.by_symbol.items():
            result["symbol"][k] = stats(v)

        for k, v in self.by_regime.items():
            result["regime"][k] = stats(v)

        return result