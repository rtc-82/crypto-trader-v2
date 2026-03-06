import sqlite3

DB_PATH = "trades.db"

def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM trades WHERE chain='multi'")
    before = cur.fetchone()[0]

    cur.execute("DELETE FROM trades WHERE chain='multi'")
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM trades WHERE chain='multi'")
    after = cur.fetchone()[0]

    conn.close()

    print(f"Removed legacy chain='multi' rows: {before - after}")

if __name__ == "__main__":
    main()