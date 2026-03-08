# research/v4_multichain_engine/config.py

from __future__ import annotations

# ============================================================
# STRATEGY CONFIG
# ============================================================

STRATEGY_CONFIG = {

    "ema_period": 50,

    "atr_period": 14,

    "slope_threshold": 0.12,

    "volatility_percentile_threshold": 0.45,

    "adx_threshold": 30,

    "breakout_lookback": 12,
}

# ============================================================
# ENGINE CONFIG
# ============================================================

ENGINE_CONFIG = {

    # =========================================
    # STARTING EQUITY
    # =========================================

    "starting_equity": 75.0,

    # =========================================
    # STRATEGY
    # =========================================

    "atr_stop_multiplier": 1.5,

    "risk_reward_ratio": 1.4,

    "trade_cooldown": 0,

    "invert_signals": True,

    # =========================================
    # RUNTIME
    # =========================================

    "loop_interval": 5,

    # =========================================
    # SAFETY
    # =========================================

    "daily_loss_limit_pct": 0.03,

    # =========================================
    # COST MODEL
    # =========================================

    "cost_r": 0.05,

    "slippage_model": {

        "enabled": True,

        "mean_r": 0.03,

        "std_r": 0.02,

        "seed": 42,

        "clip_min_r": 0.0,
    },

    # =========================================
    # PORTFOLIO RISK
    # =========================================

    "portfolio_base_risk_pct": 0.02,

    "score_lookback_trades": 120,

    # ======================================================
    # PORTFOLIO CIRCUIT BREAKER
    # ======================================================

    "portfolio_circuit_breaker_dd": 0.10,   # stop trading at 10% drawdown
    "circuit_breaker_cooldown_minutes": 240,

    # =========================================
    # POSITION LIMITS
    # =========================================

    "max_concurrent_positions": 3,

    # =========================================
    # CORRELATION CONTROL
    # =========================================

    "correlation_threshold": 0.75,

    "correlation_lookback_bars": 200,

    "correlation_min_bars": 80,

    # ======================================================
    # PHASE SWITCHING
    # ======================================================

    "phase_switch_equity": 1000.0,

    # ---------- ACCELERATION PHASE ----------

    "acceleration_risk_ladder": [

        (250, 0.0100),

        (750, 0.0115),

        (1500, 0.0125),

        (3000, 0.0135),

        (float("inf"), 0.0150),
    ],

    # ---------- PRESERVATION PHASE ----------

    "preservation_risk_ladder": [

        (2500, 0.0100),

        (5000, 0.0090),

        (10000, 0.0080),

        (float("inf"), 0.0070),
    ],

    # backward compatibility
    "risk_ladder": [

        (250, 0.0100),

        (750, 0.0115),

        (1500, 0.0125),

        (3000, 0.0135),

        (float("inf"), 0.0150),
    ],

    # ======================================================
    # KILL SWITCH
    # ======================================================

    "acceleration_kill_switch_dd": 0.18,

    "preservation_kill_switch_dd": 0.12,

    # ======================================================
    # PROFIT FACTOR THROTTLE
    # ======================================================

    "pf_rolling_window": 200,

    # acceleration phase
    "pf_pause_below_accel": 0.85,

    "pf_half_risk_below_accel": 1.00,

    "pf_resume_above_accel": 1.15,

    # preservation phase
    "pf_pause_below_preserve": 0.90,

    "pf_half_risk_below_preserve": 1.05,

    "pf_resume_above_preserve": 1.15,
}

# ============================================================
# GLOBAL RISK ENGINE
# ============================================================

GLOBAL_RISK_CONFIG = {

    # daily drawdown limit
    "max_daily_loss_pct": ENGINE_CONFIG.get(
        "daily_loss_limit_pct", 0.03
    ),

    # max trade notional vs equity
    "max_trade_fraction": 0.20,

    # max trades per hour
    "max_trades_per_hour": 6,
}

# ============================================================
# POSITION CONFIG
# ============================================================

POSITION_CONFIG = {

    "max_concurrent_positions": ENGINE_CONFIG.get(
        "max_concurrent_positions", 1
    ),

    "allow_multiple_symbols": True,

    "prevent_same_symbol_reentry": True,
}

# ============================================================
# SIGNAL RANKING
# ============================================================

SIGNAL_RANKING_CONFIG = {

    "w_slope": 0.60,

    "w_vol": 0.40,

    "require_meta": False,
}

# ============================================================
# DYNAMIC MARKET UNIVERSE
# ============================================================

UNIVERSE_CONFIG = {

    # how often universe rotates
    "refresh_interval_minutes": 240,

    # how many symbols to trade
    "universe_size": 20,
}

# ============================================================
# REGIME RISK SCALING
# ============================================================

RISK_SCALING_CONFIG = {

    "enabled": True,

    "min_mult": 0.25,

    "max_mult": 1.50,

    # slope strength scaling
    "slope": {

        "low": 0.10,

        "high": 0.35,

        "low_mult": 0.60,

        "high_mult": 1.25,
    },

    # volatility percentile scaling
    "vol": {

        "low": 0.55,

        "high": 0.85,

        "low_mult": 0.80,

        "high_mult": 1.15,
    },

    # regime based scaling
    "regime_mult": {

        "TRENDING": 1.10,

        "RANGE": 0.75,

        "UNKNOWN": 0.90,
    },
}

# ============================================================
# KELLY PORTFOLIO SIZING
# ============================================================

KELLY_CONFIG = {

    "enabled": True,

    # fraction of Kelly to use (safety)
    "kelly_fraction": 0.25,

    # minimum sample size before using Kelly
    "min_trades": 50,

    # bounds to prevent extreme sizing
    "min_mult": 0.5,
    "max_mult": 1.5,
}

# ================================
# LIQUIDITY FILTER
# ================================

LIQUIDITY_CONFIG = {

    # minimum 24h volume in USDT
    "min_volume_usdt": 10_000_000,

    # maximum spread %
    "max_spread_pct": 0.002,   # 0.2%

}

# ============================================================
# MONTE CARLO
# ============================================================

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

    # infrastructure fail thresholds
    "dd_fail_level": 0.25,

    "pf_fail_level": 1.00,
}