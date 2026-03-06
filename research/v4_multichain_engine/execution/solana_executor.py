# sniper_crypto/v4_multichain_engine/execution/solana_executor.py

import random


class SolanaExecutor:

    def __init__(self, config):
        self.price = 1.0
        self.tick = 0

        self.current_regime = "SIDEWAYS"
        self.regime_ticks_remaining = random.randint(40, 120)

        self.volatility = 0.002
        self.vol_cluster_factor = 1.0

    # ==============================
    # REGIME LOGIC
    # ==============================

    def _switch_regime(self):
        regimes = ["TREND_UP", "TREND_DOWN", "SIDEWAYS", "HIGH_VOL"]
        self.current_regime = random.choice(regimes)
        self.regime_ticks_remaining = random.randint(40, 120)

    # ==============================
    # VOLATILITY CLUSTERING
    # ==============================

    def _update_volatility_cluster(self):
        # cluster volatility randomly
        if random.random() < 0.05:
            self.vol_cluster_factor = random.uniform(1.5, 3.0)
        else:
            self.vol_cluster_factor *= 0.98

        self.vol_cluster_factor = max(1.0, min(self.vol_cluster_factor, 3.0))

    # ==============================
    # FAT TAIL SHOCKS
    # ==============================

    def _inject_tail_event(self):
        if random.random() < 0.002:  # rare shock
            shock_direction = random.choice([-1, 1])
            shock_magnitude = random.uniform(0.01, 0.03)  # 1%–3% move
            self.price += self.price * shock_direction * shock_magnitude

    # ==============================
    # PRICE EVOLUTION
    # ==============================

    def _evolve_price(self):

        base_vol = self.volatility * self.vol_cluster_factor

        if self.current_regime == "TREND_UP":
            drift = 0.0005
        elif self.current_regime == "TREND_DOWN":
            drift = -0.0005
        elif self.current_regime == "HIGH_VOL":
            drift = random.uniform(-0.0005, 0.0005)
            base_vol *= 2
        else:  # SIDEWAYS
            drift = random.uniform(-0.0003, 0.0003)

        noise = random.gauss(0, base_vol)

        self.price += self.price * (drift + noise)

        # prevent negative price
        self.price = max(0.0001, self.price)

    # ==============================
    # MAIN TICK
    # ==============================

    def get_next_price(self):

        self.tick += 1

        self.regime_ticks_remaining -= 1
        if self.regime_ticks_remaining <= 0:
            self._switch_regime()

        self._update_volatility_cluster()
        self._inject_tail_event()
        self._evolve_price()

        return {
            "price": self.price,
            "regime": self.current_regime
        }