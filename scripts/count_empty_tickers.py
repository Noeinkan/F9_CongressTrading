"""One-off: python scripts/count_empty_tickers.py (from repo root)."""
import sqlite3
from pathlib import Path

root = Path(__file__).resolve().parents[1]
conn = sqlite3.connect(root / "data" / "db" / "congress_trades.sqlite")
c = conn.cursor()
c.execute("SELECT COUNT(*) FROM transactions WHERE ticker IS NULL OR TRIM(ticker) = ''")
empty = c.fetchone()[0]
c.execute("SELECT COUNT(*) FROM transactions")
total = c.fetchone()[0]
print(f"{empty}/{total} empty tickers ({100 * empty / total:.1f}%)")
conn.close()
