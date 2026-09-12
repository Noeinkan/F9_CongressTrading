"""Remove rows an old test run wrote into the real database.

Before ``tests/conftest.py`` pinned every test to a temporary database, the
Senate and OGE ingest tests wrote into ``data/db``: fake trades attributed to
a real senator (Gary Peters), the legacy ``trades`` rows that mirror them, and
``files_ingested`` markers. Those tests read from pytest's temp directory
(``.../pytest-of-<user>/...``), where no real disclosure ever lives, so that
path is a safe signature. Idempotent: a clean database deletes nothing.
"""
from __future__ import annotations

import sqlite3

_PYTEST_PATH = "%pytest-of-%"


def delete_pytest_leftovers(conn: sqlite3.Connection) -> dict[str, int]:
    filings = conn.execute(
        "SELECT id, member_id FROM filings WHERE raw_document_path LIKE ?", (_PYTEST_PATH,)
    ).fetchall()
    filing_ids = [int(row["id"]) for row in filings]
    member_ids = {int(row["member_id"]) for row in filings}

    transactions = 0
    if filing_ids:
        marks = ", ".join("?" for _ in filing_ids)
        txn_ids = [
            int(row[0])
            for row in conn.execute(
                f"SELECT id FROM transactions WHERE filing_id IN ({marks})", filing_ids
            )
        ]
        if txn_ids:
            txn_marks = ", ".join("?" for _ in txn_ids)
            conn.execute(f"DELETE FROM review_queue WHERE transaction_id IN ({txn_marks})", txn_ids)
            conn.execute(f"DELETE FROM transaction_tags WHERE transaction_id IN ({txn_marks})", txn_ids)
            conn.execute(f"DELETE FROM transactions WHERE id IN ({txn_marks})", txn_ids)
        transactions = len(txn_ids)
        conn.execute(f"DELETE FROM filings WHERE id IN ({marks})", filing_ids)
        # A member only the test created goes too; a real one keeps its other filings.
        for member_id in member_ids:
            conn.execute(
                "DELETE FROM members WHERE id = ? AND NOT EXISTS "
                "(SELECT 1 FROM filings WHERE member_id = ?)",
                (member_id, member_id),
            )

    trades = conn.execute("DELETE FROM trades WHERE source_file LIKE ?", (_PYTEST_PATH,)).rowcount
    markers = conn.execute(
        "DELETE FROM files_ingested WHERE file_path LIKE ?", (_PYTEST_PATH,)
    ).rowcount
    conn.commit()
    return {
        "filings": len(filing_ids),
        "transactions": transactions,
        "trades": trades,
        "files_ingested": markers,
    }
