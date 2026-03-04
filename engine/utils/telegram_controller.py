import requests
import os
import sqlite3
import pandas as pd


class TelegramController:

    def __init__(self, token, chat_id):

        self.token = token
        self.chat_id = str(chat_id)

        self.offset = None

    def _get_updates(self):

        url = f"https://api.telegram.org/bot{self.token}/getUpdates"

        params = {"timeout": 1}

        if self.offset:
            params["offset"] = self.offset

        try:
            r = requests.get(url, params=params, timeout=5)
            return r.json()["result"]
        except:
            return []

    def send(self, message):

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"

        try:
            requests.post(
                url,
                json={"chat_id": self.chat_id, "text": message},
                timeout=5
            )
        except:
            pass

    def check_commands(self, equity):

        updates = self._get_updates()

        for u in updates:

            self.offset = u["update_id"] + 1

            if "message" not in u:
                continue

            msg = u["message"]

            if str(msg["chat"]["id"]) != self.chat_id:
                continue

            text = msg.get("text", "")

            # STATUS
            if text == "/status":

                self.send(
                    f"🤖 Bot running\nEquity: {equity:.2f}"
                )

            # EQUITY
            elif text == "/equity":

                self.send(f"💰 Equity: {equity:.2f}")

            # STOP
            elif text == "/stop":

                open("kill.switch", "w").close()

                self.send("🛑 Kill switch activated")

            # START
            elif text == "/start":

                if os.path.exists("kill.switch"):
                    os.remove("kill.switch")

                self.send("✅ Kill switch removed")

            # STATS
            elif text == "/stats":

                try:

                    conn = sqlite3.connect("trades.db")

                    df = pd.read_sql_query(
                        "SELECT * FROM trades WHERE exit_price IS NOT NULL",
                        conn
                    )

                    if df.empty:

                        self.send("No trades yet.")
                        return

                    total = len(df)
                    wins = len(df[df["pnl"] > 0])

                    win_rate = wins / total * 100
                    pnl = df["pnl"].sum()

                    self.send(
                        "📊 Stats\n\n"
                        f"Trades: {total}\n"
                        f"Win rate: {win_rate:.2f}%\n"
                        f"PnL: {pnl:.2f}"
                    )

                except:

                    self.send("Stats unavailable.")