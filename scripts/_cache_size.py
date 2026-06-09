import sqlite3, time
c = sqlite3.connect(r'C:\Users\andre\Downloads\F9_CongressTrading\data\db\congress_trades.sqlite')
print(time.strftime('%H:%M:%S'))
print('cached tickers:', c.execute('SELECT COUNT(DISTINCT ticker) FROM polygon_daily_bar_cache').fetchone()[0])
print('bar rows:', c.execute('SELECT COUNT(*) FROM polygon_daily_bar_cache').fetchone()[0])
