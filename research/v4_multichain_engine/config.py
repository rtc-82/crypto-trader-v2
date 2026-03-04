# research/v4_multichain_engine/config.py

# ================================
# STRATEGY CONFIG
# ================================

STRATEGY_CONFIG = {
    "ema_period": 50,
    "atr_period": 14,
    "slope_threshold": 0.4,
    "volatility_percentile_threshold": 0.7,
    "adx_threshold": 30,
    "breakout_lookback": 20,
}

# ================================
# ENGINE CONFIG (Infrastructure Mode)
# ================================

ENGINE_CONFIG = {
    "starting_equity": 75.0,

    # --- Strategy / execution ---
    "atr_stop_multiplier": 1.5,
    "risk_reward_ratio": 1.4,
    "trade_cooldown": 0,
    "invert_signals": True,

    # --- Trading cost model ---
    "cost_r": 0.05,

    # Slippage (off for baseline stability)
    "slippage_model": {
        "enabled": True,
        "mean_r": 0.03,
        "std_r": 0.02,
        "seed": 42,
        "clip_min_r": 0.0
    },

    # --- Core Portfolio Risk ---
    "portfolio_base_risk_pct": 0.01,   # 🔒 Infrastructure risk
    "score_lookback_trades": 120,
    "max_concurrent_positions": 1,

    # --- Correlation Gating ---
    "correlation_threshold": 0.75,
    "correlation_lookback_bars": 200,
    "correlation_min_bars": 80,

    # ==========================================================
    # PHASE SWITCHING
    # ==========================================================

    # Switch to preservation earlier to protect profits
    "phase_switch_equity": 200.0,

    # --- Acceleration Risk Ladder (Controlled Growth) ---
    "acceleration_risk_ladder": [
        (250, 0.0100),
        (750, 0.0115),
        (1500, 0.0125),
        (3000, 0.0135),
        (float("inf"), 0.0150),
    ],

    # --- Preservation Risk Ladder (Capital Protection) ---
    "preservation_risk_ladder": [
        (2500, 0.0100),
        (5000, 0.0090),
        (10000, 0.0080),
        (float("inf"), 0.0070),
    ],

    # Backwards compatibility (if referenced anywhere)
    "risk_ladder": [
        (250, 0.0100),
        (750, 0.0115),
        (1500, 0.0125),
        (3000, 0.0135),
        (float("inf"), 0.0150),
    ],

    # ==========================================================
    # KILL SWITCHES (Infrastructure Safety)
    # ==========================================================

    "acceleration_kill_switch_dd": 0.18,   # 18% max DD
    "preservation_kill_switch_dd": 0.12,   # 12% max DD

    # ==========================================================
    # PF THROTTLE (Stable, Not Reactive)
    # ==========================================================

    "pf_rolling_window": 200,

    # Acceleration phase
    "pf_pause_below_accel": 0.85,
    "pf_half_risk_below_accel": 1.00,
    "pf_resume_above_accel": 1.15,

    # Preservation phase
    "pf_pause_below_preserve": 0.90,
    "pf_half_risk_below_preserve": 1.05,
    "pf_resume_above_preserve": 1.15,
}

# ================================
# MONTE CARLO CONFIG
# ================================

MONTE_CARLO_CONFIG = {
    "enabled": True,
    "simulations": 1000,
    "seed": 42,

    "run_baseline": True,
    "run_cost_2x": True,
    "run_loss_clustering": True,
    "run_slippage": True,

    "slippage_mean_r": 0.03,
    "slippage_std_r": 0.02,

    "block_min": 10,
    "block_max": 30,

    # Infrastructure fail thresholds
    "dd_fail_level": 0.25,
    "pf_fail_level": 1.00,
}