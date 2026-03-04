# engine/core/trade_logger.py

from __future__ import annotations

import sqlite3
import time
from typing import Optional


class TradeLogger:
    def __init__(self, db_path: str = "trades.db") -> None:
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            cur = conn.cursor()

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

            cur.execute("CREATE INDEX IF NOT EXISTS idx_trades_ts_open ON trades(ts_open)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol)")
            conn.commit()

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