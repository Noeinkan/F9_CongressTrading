import sqlite3

conn = sqlite3.connect("data/db/congress_trades.sqlite")
print("transactions:", conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0])
print("distinct ticker:", conn.execute("SELECT COUNT(DISTINCT UPPER(ticker)) FROM transactions WHERE COALESCE(ticker,'') <> ''").fetchone()[0])
print("polygon_daily_bar_cache rows:", conn.execute("SELECT COUNT(*) FROM polygon_daily_bar_cache").fetchone()[0])
print("polygon_daily_bar_cache distinct ticker:", conn.execute("SELECT COUNT(DISTINCT ticker) FROM polygon_daily_bar_cache").fetchone()[0])
print("issuers rows:", conn.execute("SELECT COUNT(*) FROM issuers").fetchone()[0])
print("asset_resolution_cache rows:", conn.execute("SELECT COUNT(*) FROM asset_resolution_cache").fetchone()[0])
