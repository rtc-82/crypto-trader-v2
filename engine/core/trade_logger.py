from __future__ import annotations

import sqlite3
import time
from typing import Optional, List, Tuple


class TradeLogger:

    def __init__(self, db_path: str = "trades.db") -> None:
        self.db_path = db_path
        self._init_db()

    # ------------------------------------------------
    # CONNECTION
    # ------------------------------------------------

    def _connect(self) -> sqlite3.Connection:

        conn = sqlite3.connect(self.db_path, timeout=30)

        # WAL improves concurrency and crash safety
        conn.execute("PRAGMA journal_mode=WAL;")

        # Faster writes
        conn.execute("PRAGMA synchronous=NORMAL;")

        return conn

    # ------------------------------------------------
    # DATABASE INIT
    # ------------------------------------------------

    def _init_db(self) -> None:

        with self._connect() as conn:

            cur = conn.cursor()

            # -------------------------
            # TRADES TABLE
            # -------------------------

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts_open INTEGER NOT NULL,
                    ts_close INTEGER,
                    symbol TEXT NOT NULL,
                    chain TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    size REAL NOT NULL,
                    entry_price REAL NOT NULL,
                    exit_price REAL,
                    atr REAL,
                    r_multiple REAL
                )
                """
            )

            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_trades_ts_open ON trades(ts_open)"
            )

            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol)"
            )

            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_trades_chain ON trades(chain)"
            )

            # -------------------------
            # SIGNAL TABLE
            # -------------------------

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts INTEGER NOT NULL,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    price REAL,
                    atr REAL
                )
                """
            )

            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_signals_ts ON signals(ts)"
            )

            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signals(symbol)"
            )

            conn.commit()

    # ------------------------------------------------
    # SIGNAL LOGGING
    # ------------------------------------------------

    def log_signal(
        self,
        *,
        symbol: str,
        direction: str,
        price: float,
        atr: float,
        ts: Optional[int] = None,
    ) -> None:

        ts = int(ts if ts is not None else time.time())

        with self._connect() as conn:

            cur = conn.cursor()

            cur.execute(
                """
                INSERT INTO signals (ts, symbol, direction, price, atr)
                VALUES (?, ?, ?, ?, ?)
                """,
                (ts, symbol, direction, float(price), float(atr)),
            )

            conn.commit()

    # ------------------------------------------------
    # BULK SIGNAL LOGGING (performance upgrade)
    # ------------------------------------------------

    def log_signals_bulk(self, signals: List[Tuple]) -> None:
        """
        Faster batch signal logging.

        signals format:
        [(ts, symbol, direction, price, atr), ...]
        """

        with self._connect() as conn:

            cur = conn.cursor()

            cur.executemany(
                """
                INSERT INTO signals (ts, symbol, direction, price, atr)
                VALUES (?, ?, ?, ?, ?)
                """,
                signals
            )

            conn.commit()

    # ------------------------------------------------
    # TRADE ENTRY
    # ------------------------------------------------

    def log_entry(
        self,
        *,
        symbol: str,
        chain: str,
        direction: str,
        size: float,
        entry_price: float,
        atr: float,
        ts_open: Optional[int] = None,
    ) -> int:

        ts_open = int(ts_open if ts_open is not None else time.time())

        with self._connect() as conn:

            cur = conn.cursor()

            cur.execute(
                """
                INSERT INTO trades (ts_open, symbol, chain, direction, size, entry_price, atr)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (ts_open, symbol, chain, direction, float(size), float(entry_price), float(atr)),
            )

            conn.commit()

            return int(cur.lastrowid)

    # ------------------------------------------------
    # TRADE EXIT
    # ------------------------------------------------

    def log_exit(
        self,
        *,
        trade_id: int,
        exit_price: float,
        r_multiple: float,
        ts_close: Optional[int] = None,
    ) -> None:

        ts_close = int(ts_close if ts_close is not None else time.time())

        with self._connect() as conn:

            cur = conn.cursor()

            cur.execute(
                """
                UPDATE trades
                SET ts_close = ?, exit_price = ?, r_multiple = ?
                WHERE id = ?
                """,
                (ts_close, float(exit_price), float(r_multiple), int(trade_id)),
            )

            conn.commit()

    # ------------------------------------------------
    # OPEN TRADE RECOVERY (NEW)
    # ------------------------------------------------

    def get_open_trades(self):

        """
        Returns trades that are still open.
        Used for crash recovery.
        """

        with self._connect() as conn:

            cur = conn.cursor()

            cur.execute(
                """
                SELECT id, symbol, chain, direction, size, entry_price, atr, ts_open
                FROM trades
                WHERE ts_close IS NULL
                """
            )

            rows = cur.fetchall()

        return rows