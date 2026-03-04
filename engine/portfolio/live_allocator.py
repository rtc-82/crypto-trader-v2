import logging

logger = logging.getLogger("trading_engine")


class LivePortfolioAllocator:

    def __init__(self, config=None):

        config = config or {}

        self.closed_rs = []
        self.paused = False
        self.phase = "accel"

        # ==============================
        # CONFIG VALUES
        # ==============================

        self.phase_switch_equity = config.get("phase_switch_equity", 2000)

        self.risk_ladder_accel = config.get(
            "acceleration_risk_ladder",
            [
                (250, 0.020),
                (750, 0.0175),
                (1500, 0.015),
                (3000, 0.0125),
                (float("inf"), 0.010),
            ],
        )

        self.risk_ladder_preserve = config.get(
            "preservation_risk_ladder",
            [
                (2500, 0.0125),
                (5000, 0.010),
                (10000, 0.008),
                (float("inf"), 0.007),
            ],
        )

        self.max_positions = config.get("max_concurrent_positions", 3)

        # PF thresholds (phase aware)
        self.pf_pause_accel = config.get("pf_pause_below_accel", 1.0)
        self.pf_half_accel = config.get("pf_half_risk_below_accel", 1.15)
        self.pf_resume_accel = config.get("pf_resume_above_accel", 1.20)

        self.pf_pause_preserve = config.get("pf_pause_below_preserve", 1.05)
        self.pf_half_preserve = config.get("pf_half_risk_below_preserve", 1.15)
        self.pf_resume_preserve = config.get("pf_resume_above_preserve", 1.20)

        self.pf_window = config.get("pf_rolling_window", 200)

    # -------------------------------------

    def record_trade_result(self, r):

        self.closed_rs.append(r)

        if len(self.closed_rs) > self.pf_window:
            self.closed_rs.pop(0)

    # -------------------------------------

    def rolling_pf(self):

        if len(self.closed_rs) < 20:
            return 999

        gp = sum(r for r in self.closed_rs if r > 0)
        gl = sum(-r for r in self.closed_rs if r < 0)

        if gl == 0:
            return 999

        return gp / gl

    # -------------------------------------

    def current_phase(self, equity):

        if self.phase == "accel" and equity >= self.phase_switch_equity:

            logger.info("[ALLOCATOR] Switching to PRESERVATION phase")

            self.phase = "preserve"

        return self.phase

    # -------------------------------------

    def ladder_risk(self, equity):

        ladder = (
            self.risk_ladder_preserve
            if self.phase == "preserve"
            else self.risk_ladder_accel
        )

        for level, risk in ladder:

            if equity < level:
                return risk

        return ladder[-1][1]

    # -------------------------------------

    def pf_multiplier(self):

        pf = self.rolling_pf()

        # Select thresholds based on phase

        if self.phase == "preserve":

            pause = self.pf_pause_preserve
            half = self.pf_half_preserve
            resume = self.pf_resume_preserve

        else:

            pause = self.pf_pause_accel
            half = self.pf_half_accel
            resume = self.pf_resume_accel

        # Resume trading if PF recovered

        if self.paused and pf > resume:

            logger.info("[ALLOCATOR] PF recovered — trading resumed")

            self.paused = False

        # Pause trading

        if pf < pause:

            self.paused = True

            logger.warning("[ALLOCATOR] PF below threshold — trading paused")

            return 0

        # Half risk

        if pf < half:

            logger.info("[ALLOCATOR] PF below optimal — half risk")

            return 0.5

        return 1.0

    # -------------------------------------

    def allow_entry(self, equity, open_positions):

        self.current_phase(equity)

        if self.paused:

            logger.info("[ALLOCATOR] Trading paused")

            return False, 0

        if open_positions >= self.max_positions:

            logger.info("[ALLOCATOR] Max positions reached")

            return False, 0

        multiplier = self.pf_multiplier()

        base_risk = self.ladder_risk(equity)

        return True, multiplier * base_risk