# engine/portfolio/global_risk_engine.py

import time
from collections import deque


class GlobalRiskEngine:
    """
    Portfolio-level guardrails.

    Blocks trades if:
    - Daily loss exceeded
    - Trade rate exceeded
    - Trade size too large
    """

    def __init__(self, max_daily_loss_pct, max_trade_fraction, max_trades_per_hour):

        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_trade_fraction = max_trade_fraction
        self.max_trades_per_hour = max_trades_per_hour

        self.daily_start_equity = None
        self.trade_times = deque()

    # ------------------------------------------------
    # DAILY BASELINE
    # ------------------------------------------------

    def reset_daily_baseline(self, equity):
        """
        Set the equity baseline used for daily drawdown checks.
        """
        self.daily_start_equity = equity

    # ------------------------------------------------
    # REGISTER TRADE
    # ------------------------------------------------

    def on_trade_executed(self):
        """
        Record a trade timestamp for trade-rate control.
        """

        now = time.time()

        self.trade_times.append(now)

        # Remove trades older than 1 hour
        one_hour = now - 3600

        while self.trade_times and self.trade_times[0] < one_hour:
            self.trade_times.popleft()

    # ------------------------------------------------
    # CORE RISK APPROVAL
    # ------------------------------------------------

    def approve_trade(self, equity, proposed_notional):
        """
        Full risk approval logic.

        Returns a Decision object:
        {
            allowed: bool
            reason: str
        }
        """

        # ------------------------
        # DAILY LOSS CHECK
        # ------------------------

        if self.daily_start_equity:

            dd = (self.daily_start_equity - equity) / self.daily_start_equity

            if dd >= self.max_daily_loss_pct:

                return type("Decision", (), {
                    "allowed": False,
                    "reason": "daily loss exceeded"
                })()

        # ------------------------
        # TRADE RATE CHECK
        # ------------------------

        now = time.time()

        one_hour = now - 3600

        while self.trade_times and self.trade_times[0] < one_hour:
            self.trade_times.popleft()

        if len(self.trade_times) >= self.max_trades_per_hour:

            return type("Decision", (), {
                "allowed": False,
                "reason": "trade rate limit exceeded"
            })()

        # ------------------------
        # POSITION SIZE CHECK
        # ------------------------

        cap = equity * self.max_trade_fraction

        if proposed_notional > cap:

            return type("Decision", (), {
                "allowed": False,
                "reason": "trade size exceeds risk cap"
            })()

        return type("Decision", (), {
            "allowed": True,
            "reason": ""
        })()

    # ------------------------------------------------
    # COMPATIBILITY METHOD
    # ------------------------------------------------

    def allow_new_trade(self, equity):
        """
        Compatibility method used by the orchestrator.

        Uses approve_trade internally but ignores notional.
        """

        decision = self.approve_trade(
            equity=equity,
            proposed_notional=0
        )

        return decision.allowed