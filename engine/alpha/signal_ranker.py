from types import SimpleNamespace


def rank_signals(candidates, correlation_engine=None, open_symbols=None):

    """
    Advanced multi-factor signal ranking.

    Factors used:
    - slope_norm (trend strength)
    - vol_percentile (volatility regime)
    - breakout_distance (momentum strength)
    - correlation penalty (portfolio diversification)
    """

    if not candidates:
        return None

    best = None
    best_score = -1e9

    for c in candidates:

        meta = c.get("meta") or {}

        if hasattr(meta, "__dict__"):
            meta = vars(meta)

        slope = meta.get("slope_norm", 0)
        vol = meta.get("vol_percentile", 0)
        breakout = meta.get("breakout_distance", 0)

        # -----------------------------
        # Correlation penalty
        # -----------------------------
        corr_penalty = 0

        if correlation_engine and open_symbols:

            symbol = c["symbol"]

            for open_symbol in open_symbols:

                try:

                    corr = correlation_engine.get_correlation(
                        symbol,
                        open_symbol
                    )

                    if corr is not None and corr > 0.7:
                        corr_penalty += corr

                except Exception:
                    pass

        # -----------------------------
        # Final score
        # -----------------------------

        score = (
            slope * 2.0
            + vol * 1.2
            + breakout * 1.5
            - corr_penalty * 1.5
        )

        if score > best_score:

            best_score = score

            best = SimpleNamespace(
                symbol=c["symbol"],
                signal=c["signal"],
                score=score
            )

    return best