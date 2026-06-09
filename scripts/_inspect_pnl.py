"""Quick benchmark of the patched ticker_leaderboard hot loop."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

print("start", flush=True)
from src.api.repository import load_transactions
from src.api._tickers_analytics import (
    ticker_leaderboard,
    ticker_leaderboard_cached,
)

frame, _src = load_transactions()
print(f"loaded {len(frame)} rows", flush=True)

t = time.perf_counter()
board = ticker_leaderboard(frame)
print(f"ticker_leaderboard (cold): {time.perf_counter() - t:.2f}s, {len(board)} tickers", flush=True)

t = time.perf_counter()
board2 = ticker_leaderboard_cached(frame, lookback=None, quarters=None)
print(f"ticker_leaderboard_cached (warm): {time.perf_counter() - t:.4f}s, {len(board2)} tickers", flush=True)

t = time.perf_counter()
board3 = ticker_leaderboard_cached(frame, lookback=None, quarters=None)
print(f"ticker_leaderboard_cached (hit): {time.perf_counter() - t:.6f}s, {len(board3)} tickers", flush=True)
