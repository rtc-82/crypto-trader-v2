import numpy as np
import pandas as pd


class MarketRegimeEngine:
    """
    BTC Market Regime Detector

    Determines whether the market is:
    - TRENDING
    - COMPRESSION

    Based on:
    - EMA slope
    - ATR percentile
    """

    def __init__(self, df: pd.DataFrame, ema_period: int = 50, atr_period: int = 14):

        if not isinstance(df, pd.DataFrame):
            raise TypeError("MarketRegimeEngine requires a pandas DataFrame")

        required_columns = {"timestamp", "open", "high", "low", "close"}
        missing = required_columns - set(df.columns)

        if missing:
            raise ValueError(f"DataFrame missing required columns: {missing}")

        self.df = df.sort_values("timestamp").reset_index(drop=True)
        self.ema_period = ema_period
        self.atr_period = atr_period

        self._compute_indicators()

    # ==========================================================
    # Indicator Calculation
    # ==========================================================

    def _compute_indicators(self):

        # EMA
        self.df["ema"] = self.df["close"].ewm(
            span=self.ema_period,
            adjust=False
        ).mean()

        # EMA slope (normalized)
        self.df["ema_slope"] = self.df["ema"].diff()

        # ATR
        high_low = self.df["high"] - self.df["low"]
        high_close = np.abs(self.df["high"] - self.df["close"].shift())
        low_close = np.abs(self.df["low"] - self.df["close"].shift())

        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)

        self.df["atr"] = tr.rolling(self.atr_period).mean()

        # ATR percentile proxy
        self.df["atr_percentile"] = (
            self.df["atr"]
            .rolling(200)
            .apply(lambda x: np.mean(x < x.iloc[-1]), raw=False)
        )

    # ==========================================================
    # Regime Logic
    # ==========================================================

    def get_current_regime(self) -> str:
        """
        Returns:
            "TRENDING" or "COMPRESSION"
        """

        if len(self.df) < 200:
            return "UNKNOWN"

        last = self.df.iloc[-1]

        slope = last["ema_slope"]
        atr_percentile = last["atr_percentile"]

        # Simple regime rule
        if abs(slope) > 0 and atr_percentile > 0.6:
            return "TRENDING"

        return "COMPRESSION"