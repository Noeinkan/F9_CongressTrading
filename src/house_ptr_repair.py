from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from .db import (
    insert_trades,
    insert_transaction_tag,
    queue_transaction_review,
    upsert_issuer,
)
from .parse_ptr import parse_ptr_pdf_safe
from .ticker_lookup import resolve_asset
from .utils import (
    make_transaction_source_hash,
    normalize_whitespace,
    parse_amount_range,
    parse_date,
    sanitize_transaction_date,
)


def lookup_house_ptr_filing_date(conn, doc_id: str) -> str | None:
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


def backfill_house_ptr_filing_dates(conn) -> int:
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
        filing_date = lookup_house_ptr_filing_date(conn, row["doc_id"])
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


def merge_duplicate_house_ptr_filings(conn) -> int:
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


def fix_future_transaction_dates(conn) -> int:
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


def delete_invalid_house_ptr_transactions(conn) -> int:
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


def repair_house_ptr_dates(conn) -> int:
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

        filing_date = header.get("filing_date") or lookup_house_ptr_filing_date(conn, filing["doc_id"] or pdf_path.stem)
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
