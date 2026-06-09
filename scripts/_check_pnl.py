import sqlite3
con = sqlite3.connect('data/db/congress_trades.sqlite')
cur = con.cursor()

# All distinct tickers that appear on transactions (excluding blanks)
all_t = cur.execute("""
    SELECT DISTINCT ticker FROM transactions
    WHERE ticker IS NOT NULL AND TRIM(ticker) != ''
""").fetchall()
all_tickers = {r[0].strip().upper() for r in all_t}

# Tickers with at least one bar cached
cached = cur.execute("""
    SELECT DISTINCT ticker FROM polygon_daily_bar_cache
""").fetchall()
cached_tickers = {r[0].strip().upper() for r in cached}

missing = all_tickers - cached_tickers
print(f'unique tickers in transactions: {len(all_tickers)}')
print(f'unique tickers in polygon cache: {len(cached_tickers)}')
print(f'missing from cache: {len(missing)}')
print(f'coverage: {(len(cached_tickers) / max(1, len(all_tickers))) * 100:.1f}%')
print()
# How many transactions do the missing tickers account for?
rows_missing_tx = cur.execute("""
    SELECT COUNT(*) FROM transactions
    WHERE UPPER(TRIM(ticker)) IN ({})
""".format(','.join('?' * len(missing))), list(missing)).fetchone()[0]
rows_total = cur.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
print(f'transactions in cache-covered tickers: {rows_total - rows_missing_tx} / {rows_total}')
print(f'transactions in missing tickers: {rows_missing_tx} / {rows_total}')
print()
print('first 30 missing tickers:', sorted(missing)[:30])
