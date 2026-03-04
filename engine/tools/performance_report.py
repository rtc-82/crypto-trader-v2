import sqlite3
import pandas as pd


class PerformanceReport:

    def __init__(self, db_path="trades.db"):

        self.conn = sqlite3.connect(db_path)
        self.cursor = self.conn.cursor()

        # ensure table exists
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp INTEGER,
            direction TEXT,
            entry_price REAL,
            exit_price REAL,
            size REAL,
            atr REAL,
            pnl REAL
        )
        """)

        self.conn.commit()

    def load_trades(self):

        df = pd.read_sql_query(
            "SELECT * FROM trades WHERE exit_price IS NOT NULL",
            self.conn
        )

        return df

    def generate_report(self):

        df = self.load_trades()

        if df.empty:
            print("\nNo completed trades yet.\n")
            return

        total_trades = len(df)

        wins = df[df["pnl"] > 0]
        losses = df[df["pnl"] <= 0]

        win_rate = len(wins) / total_trades * 100
        total_pnl = df["pnl"].sum()

        avg_win = wins["pnl"].mean() if not wins.empty else 0
        avg_loss = losses["pnl"].mean() if not losses.empty else 0

        profit_factor = abs(wins["pnl"].sum() / losses["pnl"].sum()) if not losses.empty else float("inf")

        df["equity"] = df["pnl"].cumsum()
        df["peak"] = df["equity"].cummax()
        df["drawdown"] = df["equity"] - df["peak"]

        max_drawdown = df["drawdown"].min()

        print("\n========== PERFORMANCE REPORT ==========\n")

        print(f"Total Trades: {total_trades}")
        print(f"Win Rate: {win_rate:.2f}%")
        print(f"Total PnL: {total_pnl:.2f}")

        print(f"Average Win: {avg_win:.2f}")
        print(f"Average Loss: {avg_loss:.2f}")

        print(f"Profit Factor: {profit_factor:.2f}")
        print(f"Max Drawdown: {max_drawdown:.2f}")

        print("\n========================================\n")


if __name__ == "__main__":

    report = PerformanceReport()
    report.generate_report()