"""Report empty-ticker fill rate and top unresolved buckets (from repo root).

  .venv\\Scripts\\python.exe scripts/count_empty_tickers.py
  .venv\\Scripts\\python.exe scripts/count_empty_tickers.py --top 40
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import Counter
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))

from src.utils import normalize_key  # noqa: E402

DB_PATH = root / "data" / "db" / "congress_trades.sqlite"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top", type=int, default=30, help="Rows to show per bucket (default 30)")
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM transactions WHERE ticker IS NULL OR TRIM(ticker) = ''")
    empty = int(c.fetchone()[0])
    c.execute("SELECT COUNT(*) FROM transactions")
    total = int(c.fetchone()[0])
    pct = (100.0 * empty / total) if total else 0.0
    print(f"{empty}/{total} empty tickers ({pct:.1f}%)")
    print()

    print(f"Top {args.top} empty-ticker asset_name_raw:")
    rows = c.execute(
        """
        SELECT COALESCE(NULLIF(TRIM(asset_name_raw), ''), '(blank)') AS asset,
               COUNT(*) AS n
        FROM transactions
        WHERE ticker IS NULL OR TRIM(ticker) = ''
        GROUP BY 1
        ORDER BY n DESC, asset
        LIMIT ?
        """,
        (args.top,),
    ).fetchall()
    for row in rows:
        print(f"  {row['n']:5d}  {row['asset']}")
    print()

    tables = {
        r[0]
        for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    if "asset_resolution_cache" not in tables:
        print("(no asset_resolution_cache table)")
        conn.close()
        return

    cache_by_key: dict[str, str] = {}
    for row in c.execute(
        "SELECT asset_name_key, match_source FROM asset_resolution_cache"
    ):
        key = (row["asset_name_key"] or "").strip()
        if key and key not in cache_by_key:
            cache_by_key[key] = (row["match_source"] or "").strip() or "(none)"

    source_counts: Counter[str] = Counter()
    for row in c.execute(
        """
        SELECT asset_name_raw
        FROM transactions
        WHERE ticker IS NULL OR TRIM(ticker) = ''
        """
    ):
        key = normalize_key(row["asset_name_raw"] or "")
        source_counts[cache_by_key.get(key, "(no cache)")] += 1

    print(f"Top {args.top} empty-ticker match_source (via asset_resolution_cache):")
    for src, n in source_counts.most_common(args.top):
        print(f"  {n:5d}  {src}")

    conn.close()


if __name__ == "__main__":
    main()
