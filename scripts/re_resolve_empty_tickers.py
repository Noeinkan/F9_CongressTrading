"""Re-resolve only transactions with empty tickers (from repo root).

Usage:
  .venv\\Scripts\\python.exe scripts/re_resolve_empty_tickers.py
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import config  # noqa: F401 — load .env
from src.db import get_connection, init_db, queue_transaction_review, upsert_issuer
from src.ticker_lookup import resolve_asset
from src.utils import normalize_whitespace
from tqdm import tqdm


def main() -> None:
    conn = get_connection()
    init_db(conn)
    rows = conn.execute(
        """
        SELECT id, asset_name_raw
        FROM transactions
        WHERE COALESCE(TRIM(ticker), '') = ''
          AND COALESCE(TRIM(asset_name_raw), '') <> ''
        """
    ).fetchall()
    by_asset: dict[str, list[int]] = defaultdict(list)
    for row in rows:
        asset = normalize_whitespace(row["asset_name_raw"] or "")
        if asset:
            by_asset[asset].append(int(row["id"]))

    filled = 0
    still_empty = 0
    bar = tqdm(by_asset.items(), desc="Re-resolve empty", unit="asset")
    for i, (asset, tids) in enumerate(bar, start=1):
        resolution = resolve_asset(conn, asset, commit=False)
        ticker = normalize_whitespace(resolution.get("ticker") or "")
        issuer_id = upsert_issuer(
            conn,
            issuer_name=resolution.get("issuer_name") or asset,
            ticker=resolution.get("ticker"),
            sector=resolution.get("sector"),
            industry=resolution.get("industry"),
            asset_type=resolution.get("asset_type"),
            commit=False,
        )
        if issuer_id is None:
            still_empty += len(tids)
            continue
        review_status = normalize_whitespace(resolution.get("review_status") or "pending")
        for tid in tids:
            conn.execute(
                """
                UPDATE transactions
                SET issuer_id = ?,
                    asset_name_normalized = ?,
                    asset_type = ?,
                    ticker = CASE WHEN ? <> '' THEN ? ELSE ticker END,
                    cusip_or_figi = ?,
                    confidence_score = ?,
                    review_status = ?,
                    updated_at = datetime('now')
                WHERE id = ?
                """,
                (
                    issuer_id,
                    normalize_whitespace(resolution.get("asset_name_normalized") or ""),
                    normalize_whitespace(resolution.get("asset_type") or ""),
                    ticker,
                    ticker,
                    normalize_whitespace(resolution.get("cusip_or_figi") or ""),
                    float(resolution.get("confidence_score") or 0.0),
                    review_status,
                    tid,
                ),
            )
            if ticker:
                filled += 1
                conn.execute("DELETE FROM review_queue WHERE transaction_id = ?", (tid,))
            else:
                still_empty += 1
                if review_status != "exact_match":
                    queue_transaction_review(
                        conn,
                        transaction_id=tid,
                        reason="asset_resolution",
                        notes=f"Asset requires review: {asset}",
                        commit=False,
                    )
        if i % 10 == 0:
            conn.commit()
            bar.set_postfix(filled=filled, empty=still_empty)
    conn.commit()
    empty_left = conn.execute(
        "SELECT COUNT(*) FROM transactions WHERE COALESCE(TRIM(ticker), '') = ''"
    ).fetchone()[0]
    total = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    conn.close()
    print(f"Filled {filled:,} rows; still empty after pass: {still_empty:,}")
    print(f"DB empty tickers now: {empty_left:,}/{total:,}")


if __name__ == "__main__":
    main()
