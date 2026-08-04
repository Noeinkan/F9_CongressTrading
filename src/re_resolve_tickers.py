from __future__ import annotations

import os
from collections import defaultdict
from typing import Any

from tqdm import tqdm

from .db import queue_transaction_review, upsert_issuer
from .ticker_lookup import bulk_resolve_unique_assets_for_reconcile, resolve_asset
from .utils import normalize_whitespace


def re_resolve_all_transaction_tickers(conn) -> int:
    """Re-run resolve_asset on every transaction (e.g. after improving local ticker extraction).

    Groups rows by normalized asset text so Polygon/OpenFIGI run once per distinct asset instead
    of once per transaction (same UPDATE/review outcome, far fewer API calls and cache lookups).
    """
    rows = conn.execute("SELECT id, asset_name_raw, ticker FROM transactions").fetchall()
    by_asset: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for row in rows:
        asset = normalize_whitespace(row["asset_name_raw"] or "")
        if not asset:
            continue
        existing_ticker = normalize_whitespace(row["ticker"] or "")
        by_asset[asset].append((int(row["id"]), existing_ticker))

    count = 0
    n_tx = sum(len(v) for v in by_asset.values())
    bulk: dict[str, dict[str, Any]] | None = None
    # Prefetching every distinct asset before DB updates was fast with batched OpenFIGI mapping; with
    # /v3/search per asset it can run for hours and hit tool timeouts. Default: resolve per asset in the
    # loop (cache still dedupes). Opt in: CONGRESS_RE_RESOLVE_TICKERS_BULK=1
    use_bulk = (os.getenv("CONGRESS_RE_RESOLVE_TICKERS_BULK") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if use_bulk and (os.getenv("CONGRESS_DISABLE_RE_RESOLVE_OPENFIGI_BATCH") or "").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        bulk = bulk_resolve_unique_assets_for_reconcile(
            conn, list(dict.fromkeys(by_asset.keys())), commit=False
        )

    bar = tqdm(by_asset.items(), desc="Re-resolve tickers", unit="asset")
    for asset_i, (asset, tid_pairs) in enumerate(bar, start=1):
        bar.set_postfix_str(f"{n_tx:,} tx")
        resolution = (bulk or {}).get(asset) if bulk is not None else None
        if resolution is None:
            resolution = resolve_asset(conn, asset, commit=False)
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
            continue
        review_status_for_queue = normalize_whitespace(resolution.get("review_status") or "")
        res_norm = normalize_whitespace(resolution.get("asset_name_normalized") or "")
        res_type = normalize_whitespace(resolution.get("asset_type") or "")
        res_cusip = normalize_whitespace(resolution.get("cusip_or_figi") or "")
        res_conf = float(resolution.get("confidence_score") or 0.0)
        res_review_db = normalize_whitespace(resolution.get("review_status") or "pending")
        n_pairs = len(tid_pairs)
        for i, (tid, existing_ticker) in enumerate(tid_pairs):
            if n_pairs > 500 and i > 0 and i % 500 == 0:
                bar.set_postfix_str(f"{n_tx:,} tx · DB {i}/{n_pairs} same asset")
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
                    res_norm,
                    res_type,
                    normalize_whitespace(resolution.get("ticker") or existing_ticker or ""),
                    normalize_whitespace(resolution.get("ticker") or existing_ticker or ""),
                    res_cusip,
                    res_conf,
                    res_review_db,
                    tid,
                ),
            )
            count += 1
        # Match _set_review_reason (no parse_warning): one batched DELETE per asset when cleared from review.
        if review_status_for_queue and review_status_for_queue != "exact_match":
            for tid, _ in tid_pairs:
                queue_transaction_review(
                    conn,
                    transaction_id=tid,
                    reason="asset_resolution",
                    notes=f"Asset requires review: {asset}",
                    commit=False,
                )
        else:
            tids_only = [t[0] for t in tid_pairs]
            for off in range(0, len(tids_only), 500):
                chunk = tids_only[off : off + 500]
                placeholders = ",".join("?" * len(chunk))
                conn.execute(
                    f"DELETE FROM review_queue WHERE transaction_id IN ({placeholders})",
                    chunk,
                )
        if asset_i % 10 == 0:
            conn.commit()
    conn.commit()
    return count
