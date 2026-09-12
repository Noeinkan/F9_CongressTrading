"""SQLite reads for the notifier.

The notifier needs one thing the dashboard never asks for: *which rows are
new*. That means ``transactions.id``, which the canonical dashboard query does
not select. Rather than widen the API contract for an internal cron job, this
module keeps its own query.

The SELECT list mirrors ``src/api/_constants.SQLITE_TRANSACTION_QUERY`` and the
rows are handed to the same ``_prepare_transactions`` the dashboard uses, so an
alert and the Raw page always describe a trade identically (same amount repair,
same party overlay, same disclosure link). If a column is added there, add it
here too.
"""
from __future__ import annotations

import sqlite3

import pandas as pd

from ..api.repository import _prepare_transactions

_SELECT_BODY = """
SELECT
    t.id AS transaction_id,
    m.full_name AS member,
    f.chamber AS chamber,
    m.party AS party,
    m.state AS state,
    f.filing_type AS filing_type,
    f.filing_date AS filing_date,
    t.transaction_date AS transaction_date,
    t.owner_type AS owner_type,
    t.asset_name_raw AS asset_name_raw,
    t.asset_name_normalized AS asset_name_normalized,
    t.asset_type AS asset_type,
    COALESCE(i.issuer_name, '') AS issuer_name,
    t.ticker AS ticker,
    COALESCE(i.sector, '') AS sector,
    COALESCE(i.industry, '') AS industry,
    t.transaction_type AS transaction_type,
    t.amount_low AS amount_low,
    t.amount_high AS amount_high,
    t.amount_range_raw AS amount_range_raw,
    t.confidence_score AS confidence_score,
    t.review_status AS review_status,
    f.source_url AS source_url,
    f.raw_document_path AS raw_document_path,
    f.doc_id AS doc_id,
    t.source_hash AS source_hash
FROM transactions t
JOIN filings f ON f.id = t.filing_id
JOIN members m ON m.id = f.member_id
LEFT JOIN issuers i ON i.id = t.issuer_id
"""

_PRIOR_TRADES_QUERY = """
SELECT COUNT(*)
FROM transactions t
JOIN filings f ON f.id = t.filing_id
JOIN members m ON m.id = f.member_id
WHERE m.full_name = ?
  AND UPPER(TRIM(t.ticker)) = ?
  AND t.id <= ?
"""


def _select(where: str) -> str:
    return f"{_SELECT_BODY}{where}\nORDER BY t.id ASC\n"


def new_transaction_stats(conn: sqlite3.Connection, after_id: int) -> tuple[int, int]:
    """``(row_count, max_id)`` for transactions above the high-water mark.

    ``max_id`` falls back to ``after_id`` when nothing is new, so the caller can
    store it unconditionally.
    """
    row = conn.execute(
        "SELECT COUNT(*), COALESCE(MAX(id), ?) FROM transactions WHERE id > ?",
        (int(after_id), int(after_id)),
    ).fetchone()
    if not row:
        return 0, int(after_id)
    return int(row[0] or 0), int(row[1] or after_id)


def load_new_transactions(conn: sqlite3.Connection, after_id: int) -> pd.DataFrame:
    """Prepared frame of transactions ingested since ``after_id``."""
    raw = pd.read_sql_query(_select("WHERE t.id > ?"), conn, params=(int(after_id),))
    return _prepare_transactions(raw)


def transactions_ingested_since(conn: sqlite3.Connection, days: int) -> pd.DataFrame:
    """Prepared frame of rows whose ``created_at`` falls in the last ``days``."""
    raw = pd.read_sql_query(
        _select("WHERE t.created_at >= datetime('now', ?)"),
        conn,
        params=(f"-{int(days)} day",),
    )
    return _prepare_transactions(raw)


def prior_trade_count(
    conn: sqlite3.Connection, member: str, ticker: str, *, up_to_id: int
) -> int:
    """How many times this member traded this ticker at or before ``up_to_id``.

    Used to tag a trade as the member's first position in a name. Counting by
    id rather than date keeps the answer stable: a 2023 trade disclosed late
    should not retroactively un-flag an alert already sent.
    """
    ticker = (ticker or "").strip().upper()
    if not member or not ticker:
        return 0
    row = conn.execute(
        _PRIOR_TRADES_QUERY, (str(member), ticker, int(up_to_id))
    ).fetchone()
    return int(row[0] or 0) if row else 0


def newest_ingest_timestamp(conn: sqlite3.Connection) -> str:
    """``created_at`` of the most recently inserted transaction ('' if none)."""
    row = conn.execute("SELECT MAX(created_at) FROM transactions").fetchone()
    if not row or row[0] is None:
        return ""
    return str(row[0]).strip()


def total_transaction_count(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()
    return int(row[0] or 0) if row else 0
