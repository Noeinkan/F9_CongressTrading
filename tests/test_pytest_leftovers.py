"""Cleanup of rows an old test run wrote into the real database (src/pytest_leftovers.py)."""
from __future__ import annotations

import sqlite3

from src.db import init_db, insert_filing, insert_transaction, mark_file_ingested, upsert_member
from src.pytest_leftovers import delete_pytest_leftovers

_TEST_FILE = r"C:\Users\x\AppData\Local\Temp\pytest-of-x\pytest-258\test_ingest_senate0\uuid-a.html"
_REAL_FILE = r"C:\repo\data\raw\senate\40fbe259.html"


def _filing_with_trade(conn, member_id: int, path: str, doc_id: str) -> int:
    filing_id = insert_filing(
        conn, member_id=member_id, chamber="Senate", filing_type="PTR",
        filing_date="2026-07-05", doc_id=doc_id, source_url="",
        raw_document_path=path, source_hash=doc_id,
    )
    return insert_transaction(
        conn, filing_id=filing_id, issuer_id=None, transaction_date="2026-07-01",
        owner_type="Self", asset_name_raw="Apple Inc (AAPL)", asset_name_normalized="Apple",
        asset_type="Stock", ticker="AAPL", cusip_or_figi=None, transaction_type="P",
        amount_low=1001, amount_high=15000, amount_range_raw="$1,001 - $15,000",
        confidence_score=1.0, review_status="exact_match", source_page=None,
        source_row="0", source_hash=f"{doc_id}-0",
    )


def test_deletes_test_rows_and_keeps_the_real_member_and_filing():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    peters = upsert_member(conn, full_name="Gary C Peters", chamber="Senate", state="MI")
    real_txn = _filing_with_trade(conn, peters, _REAL_FILE, "40fbe259")
    _filing_with_trade(conn, peters, _TEST_FILE, "uuid-a")
    only_test = upsert_member(conn, full_name="Test Senator", chamber="Senate", state="ZZ")
    _filing_with_trade(conn, only_test, _TEST_FILE.replace("senate0", "senate1"), "uuid-b")
    mark_file_ingested(conn, _TEST_FILE, "abc")
    mark_file_ingested(conn, _REAL_FILE, "def")

    stats = delete_pytest_leftovers(conn)

    assert stats["filings"] == 2 and stats["transactions"] == 2 and stats["files_ingested"] == 1
    assert [row[0] for row in conn.execute("SELECT id FROM transactions")] == [real_txn]
    assert conn.execute("SELECT 1 FROM members WHERE id = ?", (peters,)).fetchone() is not None
    assert conn.execute("SELECT 1 FROM members WHERE id = ?", (only_test,)).fetchone() is None
    assert conn.execute("SELECT COUNT(*) FROM files_ingested").fetchone()[0] == 1
    assert delete_pytest_leftovers(conn)["filings"] == 0
    conn.close()
