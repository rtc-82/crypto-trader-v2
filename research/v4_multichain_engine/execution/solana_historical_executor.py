import pandas as pd


class SolanaHistoricalExecutor:

    def __init__(self, df: pd.DataFrame):

        if not isinstance(df, pd.DataFrame):
            raise TypeError("Executor requires a pandas DataFrame")

        required_columns = {
            "timestamp",
            "open",
            "high",
            "low",
            "close",
        }

        missing = required_columns - set(df.columns)

        if missing:
            raise ValueError(
                f"DataFrame missing required columns: {missing}"
            )

        self.data = df.reset_index(drop=True)
        self.index = 0
        self.total_rows = len(self.data)

    # ==========================
    # DATA ITERATION
    # ==========================

    def has_next(self) -> bool:
        return self.index < self.total_rows

    def get_next_price(self):

        if not self.has_next():
            return None

        row = self.data.iloc[self.index]
        self.index += 1

        return {
            "timestamp": row["timestamp"],
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
        }