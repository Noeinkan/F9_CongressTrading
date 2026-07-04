from __future__ import annotations

import os
import threading
import time
from collections import defaultdict
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Iterable

import requests
from tqdm import tqdm

HOUSE_INGEST_PARSE_WORKERS = int(os.getenv("HOUSE_INGEST_PARSE_WORKERS", "4"))
HOUSE_INGEST_DB_COMMIT_CHUNK = int(os.getenv("HOUSE_INGEST_DB_COMMIT_CHUNK", "25"))

from .config import (
    HOUSE_PTR_PDF_URL,
    HOUSE_RAW_DIR,
    RAW_DIR,
    START_YEAR,
    USER_AGENT,
    house_ingest_force_reparse_pdfs,
    house_ingest_skip_external_asset_lookup,
    house_ptr_auto_download_enabled,
    house_ptr_auto_download_max_filing_year,
    house_ptr_auto_download_min_filing_year,
    house_ptr_download_min_interval_seconds,
)
from .db import (
    get_connection,
    init_db,
    insert_fd_filings,
    insert_filing,
    insert_trades,
    insert_transaction,
    insert_transaction_tag,
    is_file_ingested,
    mark_file_ingested,
    queue_transaction_review,
    upsert_issuer,
    upsert_member,
)
from .parse_fd import iter_fd_files, parse_fd_txt, parse_fd_xml
from .parse_ptr import parse_ptr_pdf_safe
from .ticker_lookup import bulk_resolve_unique_assets_for_reconcile, resolve_asset
from .house_coverage import print_house_coverage_report
from .utils import (
    ensure_dirs,
    extract_house_fd_bulk_zip,
    extract_zip,
    house_fd_bulk_zip_needs_extract,
    is_house_fd_bulk_zip_path,
    make_content_hash,
    make_transaction_source_hash,
    normalize_whitespace,
    parse_amount_range,
    parse_date,
    sanitize_transaction_date,
    sha256_file,
    split_state_district,
)
from .api.jobs import CancelledError  # noqa: E402 — single source of truth, no circular import


def _check_cancel(cancel_event: threading.Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise CancelledError()


def _lookup_house_ptr_filing_date(conn, doc_id: str) -> str | None:
    row = conn.execute(
        """
        SELECT filing_date
        FROM fd_filings
        WHERE chamber = 'House' AND doc_id = ? AND COALESCE(filing_date, '') <> ''
        ORDER BY filing_date DESC, id DESC
        LIMIT 1
        """,
        (normalize_whitespace(doc_id),),
    ).fetchone()
    if row is None:
        return None
    return normalize_whitespace(row["filing_date"])


def _backfill_house_ptr_filing_dates(conn) -> int:
    rows = conn.execute(
        """
        SELECT id, doc_id
        FROM filings
        WHERE chamber = 'House' AND filing_type = 'PTR' AND COALESCE(filing_date, '') = ''
        ORDER BY id ASC
        """
    ).fetchall()
    updated = 0
    for row in rows:
        filing_date = _lookup_house_ptr_filing_date(conn, row["doc_id"])
        if not filing_date:
            continue
        try:
            conn.execute(
                "UPDATE filings SET filing_date = ?, updated_at = datetime('now') WHERE id = ?",
                (filing_date, row["id"]),
            )
            updated += 1
        except Exception:
            continue
    conn.commit()
    return updated


def _set_review_reason(
    conn,
    transaction_id: int,
    review_status: str | None,
    asset: str,
    parse_warning: str | None,
    *,
    commit: bool = True,
) -> None:
    if parse_warning:
        queue_transaction_review(
            conn,
            transaction_id=transaction_id,
            reason="parse_warning",
            notes=parse_warning,
            commit=commit,
        )
        return

    if review_status and review_status != "exact_match":
        queue_transaction_review(
            conn,
            transaction_id=transaction_id,
            reason="asset_resolution",
            notes=f"Asset requires review: {asset}",
            commit=commit,
        )
        return

    conn.execute("DELETE FROM review_queue WHERE transaction_id = ?", (transaction_id,))
    if commit:
        conn.commit()


def _apply_parsed_row_to_transaction(conn, transaction_id: int, parsed_row: dict[str, str | None], *, existing_ticker: str | None = None, filing_date: str | None = None) -> None:
    asset = normalize_whitespace(parsed_row.get("asset") or "")
    amount_range = normalize_whitespace(parsed_row.get("amount_range") or "")
    amount_low, amount_high = parse_amount_range(amount_range)
    transaction_date = sanitize_transaction_date(
        parse_date(parsed_row.get("transaction_date") or ""), filing_date
    )
    transaction_type = normalize_whitespace(parsed_row.get("transaction_type") or "")
    owner_type = normalize_whitespace(parsed_row.get("owner_type") or "")
    source_page_value = parsed_row.get("source_page")
    source_page = int(source_page_value) if source_page_value else None
    resolution = resolve_asset(conn, asset)
    issuer_id = upsert_issuer(
        conn,
        issuer_name=resolution.get("issuer_name") or asset,
        ticker=resolution.get("ticker"),
        sector=resolution.get("sector"),
        industry=resolution.get("industry"),
        asset_type=resolution.get("asset_type"),
    )
    source_hash = make_transaction_source_hash(
        None,
        source_page,
        parsed_row.get("transaction_date"),
        asset,
        parsed_row.get("transaction_type"),
        amount_range,
        parsed_row.get("owner_type"),
    )
    try:
        conn.execute(
            """
            UPDATE transactions
            SET issuer_id = ?,
                transaction_date = ?,
                owner_type = COALESCE(NULLIF(?, ''), owner_type),
                asset_name_raw = ?,
                asset_name_normalized = ?,
                asset_type = ?,
                ticker = CASE WHEN ? <> '' THEN ? ELSE ticker END,
                cusip_or_figi = ?,
                transaction_type = ?,
                amount_low = ?,
                amount_high = ?,
                amount_range_raw = ?,
                confidence_score = ?,
                review_status = ?,
                source_page = ?,
                source_hash = CASE WHEN ? <> '' THEN ? ELSE source_hash END,
                updated_at = datetime('now')
            WHERE id = ?
            """,
            (
                issuer_id,
                normalize_whitespace(transaction_date or ""),
                owner_type,
                asset,
                normalize_whitespace(resolution.get("asset_name_normalized") or ""),
                normalize_whitespace(resolution.get("asset_type") or ""),
                normalize_whitespace(resolution.get("ticker") or existing_ticker or ""),
                normalize_whitespace(resolution.get("ticker") or existing_ticker or ""),
                normalize_whitespace(resolution.get("cusip_or_figi") or ""),
                transaction_type,
                amount_low,
                amount_high,
                amount_range,
                float(resolution.get("confidence_score") or 0.0),
                normalize_whitespace(resolution.get("review_status") or "pending"),
                source_page,
                source_hash,
                source_hash,
                transaction_id,
            ),
        )
    except Exception:
        conn.execute(
            """
            UPDATE transactions
            SET issuer_id = ?,
                transaction_date = ?,
                owner_type = COALESCE(NULLIF(?, ''), owner_type),
                asset_name_raw = ?,
                asset_name_normalized = ?,
                asset_type = ?,
                ticker = CASE WHEN ? <> '' THEN ? ELSE ticker END,
                cusip_or_figi = ?,
                transaction_type = ?,
                amount_low = ?,
                amount_high = ?,
                amount_range_raw = ?,
                confidence_score = ?,
                review_status = ?,
                source_page = ?,
                updated_at = datetime('now')
            WHERE id = ?
            """,
            (
                issuer_id,
                normalize_whitespace(transaction_date or ""),
                owner_type,
                asset,
                normalize_whitespace(resolution.get("asset_name_normalized") or ""),
                normalize_whitespace(resolution.get("asset_type") or ""),
                normalize_whitespace(resolution.get("ticker") or existing_ticker or ""),
                normalize_whitespace(resolution.get("ticker") or existing_ticker or ""),
                normalize_whitespace(resolution.get("cusip_or_figi") or ""),
                transaction_type,
                amount_low,
                amount_high,
                amount_range,
                float(resolution.get("confidence_score") or 0.0),
                normalize_whitespace(resolution.get("review_status") or "pending"),
                source_page,
                transaction_id,
            ),
        )
    review_status = normalize_whitespace(resolution.get("review_status") or "")
    _set_review_reason(conn, transaction_id, review_status, asset, parsed_row.get("parse_warning"))


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


def _transaction_logical_key(
    transaction_date: str | None,
    asset_name: str | None,
    transaction_type: str | None,
    amount_range: str | None,
    owner_type: str | None,
    source_page: int | str | None,
) -> tuple[str, str, str, str, str, str]:
    return (
        normalize_whitespace(transaction_date or ""),
        normalize_whitespace(asset_name or ""),
        normalize_whitespace(transaction_type or ""),
        normalize_whitespace(amount_range or ""),
        normalize_whitespace(owner_type or ""),
        normalize_whitespace(str(source_page) if source_page is not None else ""),
    )


def _move_transaction_metadata(conn, target_transaction_id: int, source_transaction_id: int) -> None:
    review_row = conn.execute(
        "SELECT reason, status, notes FROM review_queue WHERE transaction_id = ?",
        (source_transaction_id,),
    ).fetchone()
    target_review = conn.execute(
        "SELECT 1 FROM review_queue WHERE transaction_id = ?",
        (target_transaction_id,),
    ).fetchone()
    if review_row is not None and target_review is None:
        queue_transaction_review(
            conn,
            transaction_id=target_transaction_id,
            reason=review_row["reason"],
            notes=review_row["notes"],
            status=review_row["status"],
        )

    tag_rows = conn.execute(
        "SELECT tag, value FROM transaction_tags WHERE transaction_id = ?",
        (source_transaction_id,),
    ).fetchall()
    for tag_row in tag_rows:
        insert_transaction_tag(
            conn,
            transaction_id=target_transaction_id,
            tag=tag_row["tag"],
            value=tag_row["value"],
        )

    conn.execute("DELETE FROM review_queue WHERE transaction_id = ?", (source_transaction_id,))
    conn.execute("DELETE FROM transaction_tags WHERE transaction_id = ?", (source_transaction_id,))


def _merge_duplicate_house_ptr_filings(conn) -> int:
    duplicate_groups = conn.execute(
        """
        SELECT member_id, chamber, filing_type, doc_id, raw_document_path
        FROM filings
        WHERE chamber = 'House' AND filing_type = 'PTR'
        GROUP BY member_id, chamber, filing_type, doc_id, raw_document_path
        HAVING COUNT(*) > 1
        ORDER BY MIN(id)
        """
    ).fetchall()

    merged_filings = 0
    for group in duplicate_groups:
        filings = conn.execute(
            """
            SELECT f.id, f.filing_date, COUNT(t.id) AS transaction_count
            FROM filings f
            LEFT JOIN transactions t ON t.filing_id = f.id
            WHERE f.member_id = ? AND f.chamber = ? AND f.filing_type = ?
              AND f.doc_id = ? AND f.raw_document_path = ?
            GROUP BY f.id, f.filing_date
            ORDER BY CASE WHEN COALESCE(f.filing_date, '') <> '' THEN 0 ELSE 1 END,
                     COUNT(t.id) DESC,
                     f.id ASC
            """,
            (
                group["member_id"],
                group["chamber"],
                group["filing_type"],
                group["doc_id"],
                group["raw_document_path"],
            ),
        ).fetchall()
        if len(filings) < 2:
            continue

        canonical = filings[0]
        canonical_transactions = conn.execute(
            """
            SELECT id, transaction_date, asset_name_raw, transaction_type,
                   amount_range_raw, owner_type, source_page, source_hash
            FROM transactions
            WHERE filing_id = ?
            ORDER BY id ASC
            """,
            (canonical["id"],),
        ).fetchall()
        canonical_by_key: defaultdict[tuple[str, str, str, str, str, str], list[int]] = defaultdict(list)
        canonical_by_hash: dict[str, int] = {}
        for row in canonical_transactions:
            canonical_by_key[
                _transaction_logical_key(
                    row["transaction_date"],
                    row["asset_name_raw"],
                    row["transaction_type"],
                    row["amount_range_raw"],
                    row["owner_type"],
                    row["source_page"],
                )
            ].append(int(row["id"]))
            canonical_by_hash[normalize_whitespace(row["source_hash"] or "")] = int(row["id"])

        canonical_filing_date = normalize_whitespace(canonical["filing_date"] or "")
        for duplicate in filings[1:]:
            duplicate_filing_date = normalize_whitespace(duplicate["filing_date"] or "")
            if duplicate_filing_date and not canonical_filing_date:
                conn.execute(
                    "UPDATE filings SET filing_date = ?, updated_at = datetime('now') WHERE id = ?",
                    (duplicate_filing_date, canonical["id"]),
                )
                canonical_filing_date = duplicate_filing_date

            duplicate_transactions = conn.execute(
                """
                SELECT id, transaction_date, asset_name_raw, transaction_type,
                       amount_range_raw, owner_type, source_page, source_hash
                FROM transactions
                WHERE filing_id = ?
                ORDER BY id ASC
                """,
                (duplicate["id"],),
            ).fetchall()
            for row in duplicate_transactions:
                row_id = int(row["id"])
                logical_key = _transaction_logical_key(
                    row["transaction_date"],
                    row["asset_name_raw"],
                    row["transaction_type"],
                    row["amount_range_raw"],
                    row["owner_type"],
                    row["source_page"],
                )
                duplicate_of = None
                existing_matches = canonical_by_key.get(logical_key)
                if existing_matches:
                    duplicate_of = existing_matches[0]
                else:
                    source_hash = normalize_whitespace(row["source_hash"] or "")
                    duplicate_of = canonical_by_hash.get(source_hash)

                if duplicate_of is not None:
                    _move_transaction_metadata(conn, duplicate_of, row_id)
                    conn.execute("DELETE FROM transactions WHERE id = ?", (row_id,))
                    continue

                conn.execute(
                    "UPDATE transactions SET filing_id = ?, updated_at = datetime('now') WHERE id = ?",
                    (canonical["id"], row_id),
                )
                canonical_by_key[logical_key].append(row_id)
                canonical_by_hash[normalize_whitespace(row["source_hash"] or "")] = row_id

            conn.execute("DELETE FROM filings WHERE id = ?", (duplicate["id"],))
            merged_filings += 1

        conn.commit()

    return merged_filings


def _fix_future_transaction_dates(conn) -> int:
    """Correct transaction dates that fall after their filing date (year-typo)."""
    rows = conn.execute(
        """
        SELECT t.id, t.transaction_date, f.filing_date
        FROM transactions t
        JOIN filings f ON f.id = t.filing_id
        WHERE COALESCE(t.transaction_date, '') <> ''
          AND COALESCE(f.filing_date, '') <> ''
          AND t.transaction_date > f.filing_date
        """
    ).fetchall()
    fixed = 0
    for row in rows:
        corrected = sanitize_transaction_date(row["transaction_date"], row["filing_date"])
        if corrected and corrected != row["transaction_date"]:
            conn.execute(
                "UPDATE transactions SET transaction_date = ?, updated_at = datetime('now') WHERE id = ?",
                (corrected, row["id"]),
            )
            conn.execute(
                "UPDATE trades SET transaction_date = ? WHERE transaction_date = ? AND chamber = 'House'",
                (corrected, row["transaction_date"]),
            )
            fixed += 1
    if fixed:
        conn.commit()
    return fixed


def _delete_invalid_house_ptr_transactions(conn) -> int:
    invalid_ids = [
        int(row["id"])
        for row in conn.execute(
            """
            SELECT t.id
            FROM transactions t
            JOIN filings f ON f.id = t.filing_id
            WHERE f.chamber = 'House' AND f.filing_type = 'PTR'
              AND COALESCE(t.transaction_date, '') = ''
            """
        ).fetchall()
    ]
    if not invalid_ids:
        return 0

    placeholders = ", ".join("?" for _ in invalid_ids)
    conn.execute(f"DELETE FROM review_queue WHERE transaction_id IN ({placeholders})", invalid_ids)
    conn.execute(f"DELETE FROM transaction_tags WHERE transaction_id IN ({placeholders})", invalid_ids)
    conn.execute(f"DELETE FROM transactions WHERE id IN ({placeholders})", invalid_ids)
    conn.commit()
    return len(invalid_ids)


def _repair_house_ptr_dates(conn) -> int:
    filings = conn.execute(
        """
        SELECT f.id, f.doc_id, f.raw_document_path, f.filing_date, m.full_name
        FROM filings f
        JOIN members m ON m.id = f.member_id
        WHERE f.chamber = 'House' AND f.filing_type = 'PTR'
          AND (
              COALESCE(f.filing_date, '') = ''
              OR EXISTS (
                  SELECT 1
                  FROM transactions t
                  WHERE t.filing_id = f.id AND COALESCE(t.transaction_date, '') = ''
              )
          )
        ORDER BY f.id ASC
        """
    ).fetchall()

    repaired = 0
    for filing in filings:
        pdf_path = Path(filing["raw_document_path"])
        if not pdf_path.exists():
            continue

        try:
            header, parsed_rows = parse_ptr_pdf_safe(pdf_path)
        except Exception as exc:
            print(f"Skipping repair for unreadable House PTR PDF {pdf_path}: {exc}")
            continue
        meaningful_rows = [row for row in parsed_rows if normalize_whitespace(row.get("asset") or "")]
        existing_rows = conn.execute(
            """
            SELECT id, asset_name_raw, ticker, review_status, transaction_date, owner_type, source_page
            FROM transactions
            WHERE filing_id = ?
            ORDER BY COALESCE(source_page, 0), CAST(COALESCE(source_row, '0') AS INTEGER), id
            """,
            (filing["id"],),
        ).fetchall()
        if not meaningful_rows or not existing_rows:
            continue

        parsed_by_asset: dict[str, list[dict[str, str | None]]] = defaultdict(list)
        parsed_by_page: dict[str, list[dict[str, str | None]]] = defaultdict(list)
        for parsed_row in meaningful_rows:
            parsed_by_asset[normalize_whitespace(parsed_row.get("asset") or "")].append(parsed_row)
            parsed_by_page[normalize_whitespace(parsed_row.get("source_page") or "")].append(parsed_row)

        filing_date = header.get("filing_date") or _lookup_house_ptr_filing_date(conn, filing["doc_id"] or pdf_path.stem)
        if filing_date and filing_date != normalize_whitespace(filing["filing_date"]):
            try:
                conn.execute(
                    "UPDATE filings SET filing_date = ?, updated_at = datetime('now') WHERE id = ?",
                    (filing_date, filing["id"]),
                )
            except Exception as exc:
                print(f"Skipping filing-date update for {pdf_path}: {exc}")

        conn.execute(
            "DELETE FROM trades WHERE chamber = 'House' AND source_file = ?",
            (str(pdf_path),),
        )

        to_insert = []
        matched_rows = 0
        for existing_row in existing_rows:
            asset_key = normalize_whitespace(existing_row["asset_name_raw"] or "")
            candidates = parsed_by_asset.get(asset_key) or []
            parsed_row = candidates.pop(0) if candidates else None
            if parsed_row is None and not normalize_whitespace(existing_row["transaction_date"] or ""):
                page_key = normalize_whitespace(str(existing_row["source_page"] or ""))
                page_candidates = parsed_by_page.get(page_key) or []
                owner_key = normalize_whitespace(existing_row["owner_type"] or "")
                preferred = next(
                    (
                        candidate
                        for candidate in page_candidates
                        if not owner_key or normalize_whitespace(candidate.get("owner_type") or "") == owner_key
                    ),
                    None,
                )
                if preferred is not None:
                    parsed_row = preferred
                    page_candidates.remove(preferred)
            if parsed_row is None:
                continue

            asset = normalize_whitespace(parsed_row.get("asset") or "")
            transaction_date = sanitize_transaction_date(
                parse_date(parsed_row.get("transaction_date") or ""), filing_date
            )
            amount_range = normalize_whitespace(parsed_row.get("amount_range") or "")
            transaction_type = normalize_whitespace(parsed_row.get("transaction_type") or "")

            _apply_parsed_row_to_transaction(
                conn,
                existing_row["id"],
                parsed_row,
                existing_ticker=existing_row["ticker"],
                filing_date=filing_date,
            )

            source_page_key = normalize_whitespace(parsed_row.get("source_page") or "")
            page_candidates = parsed_by_page.get(source_page_key) or []
            if page_candidates:
                try:
                    page_candidates.remove(parsed_row)
                except ValueError:
                    pass
            to_insert.append(
                {
                    "member": normalize_whitespace(header.get("member") or filing["full_name"]),
                    "chamber": "House",
                    "filing_date": filing_date,
                    "transaction_date": transaction_date,
                    "asset": asset,
                    "ticker": normalize_whitespace(existing_row["ticker"] or ""),
                    "transaction_type": transaction_type,
                    "amount_range": amount_range,
                    "source_url": "",
                    "source_file": str(pdf_path),
                }
            )
            matched_rows += 1

        insert_trades(conn, to_insert)
        conn.commit()
        repaired += matched_rows

    return repaired


def _download_zip(url: str, dest: Path) -> Path:
    headers = {"User-Agent": USER_AGENT}
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, headers=headers, stream=True, timeout=60) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("Content-Length", 0))
        with dest.open("wb") as f, tqdm(total=total, unit="B", unit_scale=True, desc=dest.name) as pbar:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    pbar.update(len(chunk))
    return dest


def _download_house_ptr_pdf(year: int, doc_id: str, dest: Path) -> bool:
    url = HOUSE_PTR_PDF_URL.format(year=year, doc_id=doc_id)
    headers = {"User-Agent": USER_AGENT}
    dest.parent.mkdir(parents=True, exist_ok=True)

    try:
        with requests.get(url, headers=headers, stream=True, timeout=60) as resp:
            if resp.status_code == 404:
                return False
            resp.raise_for_status()
            if "pdf" not in (resp.headers.get("Content-Type") or "").lower():
                return False

            total = int(resp.headers.get("Content-Length", 0))
            # DocID spesso inizia con "200…" (non e l'anno 2002): mostra filing year nella barra.
            pbar_desc = f"{year}/{doc_id}.pdf"
            with dest.open("wb") as f, tqdm(total=total, unit="B", unit_scale=True, desc=pbar_desc) as pbar:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        pbar.update(len(chunk))
        return True
    except requests.RequestException:
        if dest.exists():
            dest.unlink(missing_ok=True)
        return False


def _download_house_ptr_pdfs(
    fd_rows: Iterable[dict[str, str | None]],
    cancel_event: threading.Event | None = None,
    progress_hook: Callable[[str, int, int], None] | None = None,
) -> int:
    if not house_ptr_auto_download_enabled():
        return 0

    min_filing_year = house_ptr_auto_download_min_filing_year()
    max_filing_year = house_ptr_auto_download_max_filing_year()
    targets: list[tuple[int, str, Path]] = []
    seen: set[tuple[int, str]] = set()

    for row in fd_rows:
        if normalize_whitespace(row.get("filing_type") or "").upper() != "P":
            continue
        doc_id = normalize_whitespace(row.get("doc_id") or "")
        year_text = normalize_whitespace(row.get("year") or "")
        if not doc_id or not year_text.isdigit():
            continue
        year = int(year_text)
        if year < min_filing_year or year > max_filing_year:
            continue
        key = (year, doc_id)
        if key in seen:
            continue
        seen.add(key)
        dest = HOUSE_RAW_DIR / str(year) / f"{doc_id}.pdf"
        if dest.exists():
            continue
        targets.append((year, doc_id, dest))

    interval = house_ptr_download_min_interval_seconds()
    downloaded = 0
    total_targets = len(targets)
    if progress_hook is not None:
        progress_hook("Downloading House PTR PDFs", 0, total_targets, unit="PTR files")
    for i, (year, doc_id, dest) in enumerate(targets):
        if cancel_event is not None and cancel_event.is_set():
            raise CancelledError()
        if i > 0 and interval > 0:
            time.sleep(interval)
        if _download_house_ptr_pdf(year, doc_id, dest):
            downloaded += 1
            if downloaded % 50 == 0:
                print(f"PTR scaricati finora: {downloaded}...", flush=True)
        if progress_hook is not None:
            progress_hook(
                f"PTR {year}/{doc_id}",
                i + 1,
                total_targets,
                unit="PTR files",
            )
    return downloaded


def _process_pdf_batch(
    conn,
    pdf_paths: list[Path],
    fd_lookup: dict[str, dict[str, str | None]],
    start_index: int,
    total_pdfs: int,
) -> tuple[int, int]:
    """Parse a chunk of PDFs (parallel, in a process pool) and persist their transactions.

    Returns ``(parsed_count, persisted_count)``. Each call to this function ends with a single
    explicit ``conn.commit()`` so a crash mid-run keeps the dashboard up-to-date with everything
    up to the last completed batch.
    """
    if not pdf_paths:
        return 0, 0

    # Step 1: parse PDFs in a process pool. pdfplumber is mostly I/O + regex and the per-call
    # ProcessPoolExecutor in parse_ptr_pdf_safe pays a fork cost; we share one pool here.
    parsed: list[tuple[Path, str, dict[str, str | None], list[dict[str, str | None]]]] = []
    parsed_count = 0
    max_workers = max(1, min(HOUSE_INGEST_PARSE_WORKERS, len(pdf_paths)))
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        future_to_path = {
            executor.submit(parse_ptr_pdf_safe, p): (idx, p)
            for idx, p in enumerate(pdf_paths)
        }
        for future in as_completed(future_to_path):
            idx, pdf_path = future_to_path[future]
            try:
                header, rows = future.result()
            except Exception as exc:
                print(
                    f"  ✗ PDF {start_index + idx + 1}/{total_pdfs}: {pdf_path.name} — errore: {exc}",
                    flush=True,
                )
                continue
            parsed.append((pdf_path, sha256_file(pdf_path), header, rows))
            parsed_count += 1

    if not parsed:
        return 0, 0

    # Step 2: bulk-resolve distinct assets once for the whole chunk (cuts Polygon/OpenFIGI calls
    # by N where N is the avg transactions-per-PDF in the chunk).
    distinct_assets: dict[str, None] = {}
    for _pdf, _sha, header, rows in parsed:
        for row in rows:
            asset = normalize_whitespace(row.get("asset") or "")
            if asset:
                distinct_assets[asset] = None
    bulk = bulk_resolve_unique_assets_for_reconcile(
        conn, list(distinct_assets.keys()), commit=False
    )

    # Step 3: persist everything on the main thread (serial DB writes).
    persisted = 0
    for pdf_path, sha, header, rows in parsed:
        member = header.get("member") or fd_lookup.get(pdf_path.stem, {}).get("member") or pdf_path.stem
        _fd_hint = fd_lookup.get(pdf_path.stem, {})
        _filing_hint = header.get("filing_date") or _fd_hint.get("filing_date") or "?"
        _txn_count = len([r for r in rows if (r.get("asset") or "").strip()])
        print(
            f"  PDF {start_index + pdf_paths.index(pdf_path) + 1}/{total_pdfs}: {pdf_path.name} | "
            f"{member} | filed {_filing_hint} | {_txn_count} txn",
            flush=True,
        )
        member = header.get("member") or pdf_path.stem
        filing_date = header.get("filing_date") or _lookup_house_ptr_filing_date(conn, pdf_path.stem)
        source_url = ""
        member_id = upsert_member(conn, full_name=normalize_whitespace(member), chamber="House")
        filing_id = insert_filing(
            conn,
            member_id=member_id,
            chamber="House",
            filing_type="PTR",
            filing_date=filing_date,
            doc_id=pdf_path.stem,
            source_url=source_url,
            raw_document_path=str(pdf_path),
            source_hash=sha,
        )
        to_insert = []
        for index, row in enumerate(rows):
            asset = normalize_whitespace(row.get("asset") or "")
            if not asset:
                continue
            resolution = bulk.get(asset) or resolve_asset(conn, asset, commit=False)
            amount_range = normalize_whitespace(row.get("amount_range") or "")
            amount_low, amount_high = parse_amount_range(amount_range)
            source_page_value = row.get("source_page")
            source_page = int(source_page_value) if source_page_value else None
            issuer_id = upsert_issuer(
                conn,
                issuer_name=resolution.get("issuer_name") or asset,
                ticker=resolution.get("ticker"),
                sector=resolution.get("sector"),
                industry=resolution.get("industry"),
                asset_type=resolution.get("asset_type"),
                commit=False,
            )
            transaction_id = insert_transaction(
                conn,
                filing_id=filing_id,
                issuer_id=issuer_id,
                transaction_date=sanitize_transaction_date(
                    parse_date(row.get("transaction_date") or ""), filing_date
                ),
                owner_type=row.get("owner_type"),
                asset_name_raw=asset,
                asset_name_normalized=resolution.get("asset_name_normalized"),
                asset_type=resolution.get("asset_type"),
                ticker=resolution.get("ticker"),
                cusip_or_figi=resolution.get("cusip_or_figi"),
                transaction_type=normalize_whitespace(row.get("transaction_type") or ""),
                amount_low=amount_low,
                amount_high=amount_high,
                amount_range_raw=amount_range,
                confidence_score=float(resolution.get("confidence_score") or 0.0),
                review_status=resolution.get("review_status"),
                source_page=source_page,
                source_row=str(index),
                source_hash=make_transaction_source_hash(
                    sha,
                    source_page,
                    row.get("transaction_date"),
                    asset,
                    row.get("transaction_type"),
                    amount_range,
                    row.get("owner_type"),
                ),
            )
            review_status = resolution.get("review_status")
            if review_status != "exact_match":
                if review_status == "fuzzy_match":
                    review_notes = (
                        f"Fuzzy asset match: {asset} -> "
                        f"{resolution.get('issuer_name') or asset} ({resolution.get('ticker') or 'no ticker'})"
                    )
                else:
                    review_notes = f"Asset requires manual review: {asset}"
                queue_transaction_review(
                    conn,
                    transaction_id=transaction_id,
                    reason="asset_resolution",
                    notes=review_notes,
                    commit=False,
                )
            if row.get("parse_warning"):
                queue_transaction_review(
                    conn,
                    transaction_id=transaction_id,
                    reason="parse_warning",
                    notes=row.get("parse_warning"),
                    commit=False,
                )
            if resolution.get("sector"):
                insert_transaction_tag(
                    conn,
                    transaction_id=transaction_id,
                    tag="sector",
                    value=str(resolution.get("sector")),
                    # NB: insert_transaction_tag commits internally; safe to call here.
                )
            if resolution.get("industry"):
                insert_transaction_tag(
                    conn,
                    transaction_id=transaction_id,
                    tag="industry",
                    value=str(resolution.get("industry")),
                )
            to_insert.append(
                {
                    "member": normalize_whitespace(member),
                    "chamber": "House",
                    "filing_date": filing_date,
                    "transaction_date": sanitize_transaction_date(
                        parse_date(row.get("transaction_date") or ""), filing_date
                    ),
                    "asset": asset,
                    "ticker": resolution.get("ticker"),
                    "transaction_type": normalize_whitespace(row.get("transaction_type") or ""),
                    "amount_range": amount_range,
                    "source_url": source_url,
                    "source_file": str(pdf_path),
                }
            )
        insert_trades(conn, to_insert)
        mark_file_ingested(conn, str(pdf_path), sha)
        persisted += 1

    conn.commit()
    return parsed_count, persisted


def _extract_local_zip_files() -> None:
    zip_paths = list(HOUSE_RAW_DIR.glob("*.zip")) + list(RAW_DIR.glob("*.zip"))
    for zip_path in zip_paths:
        name = zip_path.name.lower()
        if zip_path.parent == RAW_DIR and "senate" in name:
            continue
        dest_dir = HOUSE_RAW_DIR / zip_path.stem
        if is_house_fd_bulk_zip_path(zip_path):
            if house_fd_bulk_zip_needs_extract(zip_path, dest_dir):
                extract_house_fd_bulk_zip(zip_path, dest_dir)
        else:
            extract_zip(zip_path, dest_dir)


def ingest_house(
    cancel_event: threading.Event | None = None,
    progress_hook: Callable[[str, int, int], None] | None = None,
) -> None:
    ensure_dirs([HOUSE_RAW_DIR])
    conn = get_connection()
    init_db(conn)
    _check_cancel(cancel_event)
    merged_filings = _merge_duplicate_house_ptr_filings(conn)
    if merged_filings:
        print(f"Consolidati {merged_filings} filing PTR House duplicati.")
    backfilled_filing_dates = _backfill_house_ptr_filing_dates(conn)
    if backfilled_filing_dates:
        print(f"Backfillate {backfilled_filing_dates} filing_date PTR House da FD metadata.")
    repaired_rows = _repair_house_ptr_dates(conn)
    if repaired_rows:
        print(f"Riparate {repaired_rows} transazioni PTR House con date mancanti.")
    fixed_future_dates = _fix_future_transaction_dates(conn)
    if fixed_future_dates:
        print(f"Corrected {fixed_future_dates} transaction(s) with future dates (year-typo).")
    deleted_invalid_rows = _delete_invalid_house_ptr_transactions(conn)
    if deleted_invalid_rows:
        print(f"Rimosse {deleted_invalid_rows} righe PTR House non valide residue.")

    _extract_local_zip_files()
    _check_cancel(cancel_event)

    fd_rows: list[dict[str, str | None]] = []
    new_fd_rows: list[dict[str, str | None]] = []
    for fd_path in iter_fd_files(HOUSE_RAW_DIR):
        if fd_path.suffix.lower() not in {".txt", ".xml"}:
            continue
        if fd_path.suffix.lower() == ".txt":
            parsed_rows = list(parse_fd_txt(fd_path, "House"))
        else:
            parsed_rows = list(parse_fd_xml(fd_path, "House"))
        fd_rows.extend(parsed_rows)

        sha = sha256_file(fd_path)
        if is_file_ingested(conn, str(fd_path), sha):
            continue
        new_fd_rows.extend(parsed_rows)
        mark_file_ingested(conn, str(fd_path), sha)
    if new_fd_rows:
        insert_fd_filings(conn, new_fd_rows)
        for row in new_fd_rows:
            state, district = split_state_district(row.get("state_district"))
            member_id = upsert_member(
                conn,
                full_name=row.get("member") or "Unknown Member",
                chamber="House",
                state=state,
                district=district,
            )
            insert_filing(
                conn,
                member_id=member_id,
                chamber="House",
                filing_type=row.get("filing_type") or "FD",
                filing_date=row.get("filing_date"),
                doc_id=row.get("doc_id"),
                source_url="",
                raw_document_path=row.get("source_file") or "",
                source_hash=make_content_hash(row.get("source_file"), row.get("doc_id"), row.get("filing_date")),
            )

    downloaded_count = _download_house_ptr_pdfs(
        fd_rows,
        cancel_event=cancel_event,
        progress_hook=progress_hook,
    )
    if downloaded_count:
        print(f"Scaricati {downloaded_count} PTR House automaticamente.")
    elif not house_ptr_auto_download_enabled():
        print("Autodownload PTR House disattivato (imposta HOUSE_PTR_AUTO_DOWNLOAD=1 per riattivarlo).")
    else:
        print(
            "Nessun nuovo PTR House scaricato dal Clerk (PDF gia presenti, nessuna riga P nei metadata, "
            f"o anni fuori da [{house_ptr_auto_download_min_filing_year()}, {house_ptr_auto_download_max_filing_year()}] per filing Year)."
        )

    ptr_paths = sorted(HOUSE_RAW_DIR.rglob("*.pdf"), key=lambda p: str(p).casefold())
    if not ptr_paths:
        print("Nessun PDF trovato in data/raw/house/. Nessun PTR House scaricabile automaticamente dai metadata disponibili.")
        print_house_coverage_report(conn)
        conn.close()
        return

    total_pdfs = len(ptr_paths)
    print(f"Trovati {total_pdfs} PDF PTR in {HOUSE_RAW_DIR}; avvio parsing...", flush=True)
    if house_ingest_force_reparse_pdfs():
        print("Modalita HOUSE_INGEST_FORCE_REPARSE_PDFS: ogni PDF verra riparsato anche se gia ingerito.", flush=True)
    if not house_ingest_skip_external_asset_lookup() and total_pdfs > 80:
        print(
            "Suggerimento: con molti PDF la risoluzione ticker (Polygon) puo richiedere molto tempo. "
            "Per un ingest veloce: $env:HOUSE_INGEST_SKIP_EXTERNAL_ASSET_LOOKUP='1' poi rilancia senza per arricchire.",
            flush=True,
        )

    fd_lookup: dict[str, dict[str, str | None]] = {}
    for _fdr in fd_rows:
        _doc = _fdr.get("doc_id")
        if _doc and _doc not in fd_lookup:
            fd_lookup[_doc] = _fdr

    skipped = 0
    parsed_count = 0
    persisted_count = 0

    # Pre-filter: only PDFs that need parsing get queued. With FORCE_REPARSE_PDFS set, all of them
    # are queued; without it, anything already in files_ingested (matching sha) is skipped.
    pending: list[tuple[int, Path]] = []
    for pdf_index, pdf_path in enumerate(ptr_paths):
        sha = sha256_file(pdf_path)
        if not house_ingest_force_reparse_pdfs() and is_file_ingested(conn, str(pdf_path), sha):
            skipped += 1
            continue
        pending.append((pdf_index, pdf_path))
    if skipped:
        print(f"Skip {skipped} PDF gia ingeriti (HOUSE_INGEST_FORCE_REPARSE_PDFS non attivo).", flush=True)

    if not pending:
        print("Nessun PDF da processare.", flush=True)
    else:
        chunk = max(1, HOUSE_INGEST_DB_COMMIT_CHUNK)
        batches_total = (len(pending) + chunk - 1) // chunk
        if progress_hook is not None:
            progress_hook("Parsing House PTR PDFs", 0, len(pending), unit="PDFs")
        for batch_num, batch_start in enumerate(range(0, len(pending), chunk), start=1):
            # Check cancel between batches: in-flight ProcessPoolExecutor work
            # in `_process_pdf_batch` cannot be interrupted cleanly, but we can
            # bail out before submitting the next batch so the job ends within
            # at most one chunk's worth of latency after the user clicks Cancel.
            _check_cancel(cancel_event)
            batch = pending[batch_start : batch_start + chunk]
            batch_paths = [p for _idx, p in batch]
            batch_start_index = batch[0][0]
            t0 = time.time()
            batch_parsed, batch_persisted = _process_pdf_batch(
                conn,
                batch_paths,
                fd_lookup,
                batch_start_index,
                total_pdfs,
            )
            parsed_count += batch_parsed
            persisted_count += batch_persisted
            elapsed = time.time() - t0
            done = min(batch_start + chunk, len(pending))
            print(
                f"  [batch {done}/{len(pending)}] parsed={batch_parsed} persisted={batch_persisted} "
                f"in {elapsed:.1f}s — commit eseguito, dati visibili al dashboard.",
                flush=True,
            )
            if progress_hook is not None:
                progress_hook(
                    f"House PTR batch {batch_num}/{batches_total}",
                    batch_num,
                    batches_total,
                    unit="batches",
                )
                progress_hook(
                    "Parsing House PTR PDFs",
                    done,
                    len(pending),
                    unit="PDFs",
                )

    print(
        f"House PTR completato: {parsed_count} PDF parsati, {persisted_count} persistiti, "
        f"{skipped} gia ingeriti (skip), {total_pdfs} totali.",
        flush=True,
    )
    print_house_coverage_report(conn)
    conn.close()


if __name__ == "__main__":
    ingest_house()
