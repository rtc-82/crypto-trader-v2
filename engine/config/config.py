STRATEGY_CONFIG = {
    # Conservative V2 trend / breakout profile
    "ema_period": 100,
    "atr_period": 14,
    "slope_threshold": 0.60,
    "volatility_percentile_threshold": 0.80,
    "adx_threshold": 32,
    "breakout_lookback": 48,

    # Mean reversion effectively disabled for V2
    "bb_period": 40,
    "z_entry": 99.0,
    "max_atr_percentile_for_mr": 0.0,
}

ENGINE_CONFIG = {
    # Portfolio / runtime
    "starting_equity": 75.0,
    "loop_interval": 5,
    "portfolio_base_risk_pct": 0.0040,

    # Trade mechanics
    "atr_stop_multiplier": 2.0,
    "risk_reward_ratio": 2.0,
    "trade_cooldown": 0,
    "trade_cooldown_sec": 14400,       # 4h
    "loser_cooldown_sec": 43200,       # 12h
    "hard_loser_cooldown_sec": 86400,  # 24h
    "max_hold_seconds": 259200,        # 72h
    "invert_signals": False,

    # Safety
    "daily_loss_limit_pct": 0.015,
    "portfolio_circuit_breaker_dd": 0.06,
    "circuit_breaker_cooldown_minutes": 240,

    # Execution / ops
    "executor_timeout_sec": 20,
    "executor_retries": 2,
    "liquidity_ttl_sec": 300,

    # Portfolio controls
    "score_lookback_trades": 120,
    "max_concurrent_positions": 1,
    "correlation_threshold": 0.72,
    "correlation_lookback_bars": 250,
    "correlation_min_bars": 100,
    "phase_switch_equity": 200.0,

    # Friction model
    "cost_r": 0.05,
    "slippage_model": {
        "enabled": True,
        "mean_r": 0.03,
        "std_r": 0.02,
        "seed": 42,
        "clip_min_r": 0.0,
    },

    # Risk ladders
    "acceleration_risk_ladder": [
        (250, 0.0100),
        (750, 0.0110),
        (1500, 0.0120),
        (3000, 0.0130),
        (float("inf"), 0.0140),
    ],
    "preservation_risk_ladder": [
        (2500, 0.0100),
        (5000, 0.0090),
        (10000, 0.0080),
        (float("inf"), 0.0070),
    ],

    # Compatibility alias
    "risk_ladder": [
        (250, 0.0100),
        (750, 0.0110),
        (1500, 0.0120),
        (3000, 0.0130),
        (float("inf"), 0.0140),
    ],

    # Kill switches
    "acceleration_kill_switch_dd": 0.18,
    "preservation_kill_switch_dd": 0.12,

    # PF throttle
    "pf_rolling_window": 200,
    "pf_pause_below_accel": 0.85,
    "pf_half_risk_below_accel": 1.00,
    "pf_resume_above_accel": 1.15,
    "pf_pause_below_preserve": 0.90,
    "pf_half_risk_below_preserve": 1.05,
    "pf_resume_above_preserve": 1.15,
}

GLOBAL_RISK_CONFIG = {
    "max_daily_loss_pct": ENGINE_CONFIG.get("daily_loss_limit_pct", 0.015),
    "max_trade_fraction": 0.05,
    "max_trades_per_hour": 1,
}

POSITION_CONFIG = {
    "max_concurrent_positions": ENGINE_CONFIG.get("max_concurrent_positions", 1),
    "allow_multiple_symbols": False,
    "prevent_same_symbol_reentry": True,
}

SIGNAL_RANKING_CONFIG = {
    "w_slope": 0.70,
    "w_vol": 0.30,
    "require_meta": False,
}

UNIVERSE_CONFIG = {
    "refresh_interval_minutes": 240,
    "universe_size": 1,
}

RISK_SCALING_CONFIG = {
    "enabled": True,
    "min_mult": 0.40,
    "max_mult": 1.05,
    "slope": {
        "low": 0.25,
        "high": 0.60,
        "low_mult": 0.85,
        "high_mult": 1.00,
    },
    "vol": {
        "low": 0.60,
        "high": 0.90,
        "low_mult": 0.80,
        "high_mult": 1.00,
    },
    "regime_mult": {
        "TRENDING": 1.00,
        "COMPRESSION": 0.25,
        "NEUTRAL": 0.30,
        "RANGE": 0.40,
        "UNKNOWN": 0.40,
    },
}

KELLY_CONFIG = {
    "enabled": False,
    "kelly_fraction": 0.25,
    "min_trades": 50,
    "min_mult": 0.5,
    "max_mult": 1.5,
}

LIQUIDITY_CONFIG = {
    "min_volume_usdt": 20_000_000,
    "max_spread_pct": 0.002,
}