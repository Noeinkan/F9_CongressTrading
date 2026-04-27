from __future__ import annotations

from pathlib import Path

import pytest

from src.db import (
    get_connection,
    init_db,
    insert_filing,
    insert_transaction,
    queue_transaction_review,
    upsert_issuer,
    upsert_member,
)
from src.ingest_house import re_resolve_all_transaction_tickers


def _seed_member_and_filing(conn) -> int:
    mid = upsert_member(conn, full_name="Test Member", chamber="House", state="CA", district="1")
    return insert_filing(
        conn,
        member_id=mid,
        chamber="House",
        filing_type="PTR",
        filing_date="2024-01-01",
        doc_id="doc1",
        source_url="",
        raw_document_path="/tmp/x.pdf",
        source_hash="h1",
    )


def _insert_tx(
    conn,
    *,
    filing_id: int,
    asset_raw: str,
    source_row: str,
    ticker: str = "",
) -> int:
    return insert_transaction(
        conn,
        filing_id=filing_id,
        issuer_id=None,
        transaction_date="2024-01-02",
        owner_type="",
        asset_name_raw=asset_raw,
        asset_name_normalized="",
        asset_type="",
        ticker=ticker,
        cusip_or_figi="",
        transaction_type="purchase",
        amount_low=None,
        amount_high=None,
        amount_range_raw="",
        confidence_score=0.0,
        review_status="pending",
        source_page=1,
        source_row=source_row,
        source_hash=None,
    )


@pytest.fixture
def db_conn(tmp_path: Path):
    path = tmp_path / "test.sqlite"
    conn = get_connection(path)
    init_db(conn)
    yield conn
    conn.close()


def test_re_resolve_parenthetical_clears_review_queue_in_batches(db_conn):
    """Same asset, multiple txs: batched DELETE must remove all review_queue rows (chunks of 500)."""
    filing_id = _seed_member_and_filing(db_conn)
    asset = "Example Corp (EXM) [ST]"
    n = 505
    tids: list[int] = []
    for i in range(n):
        tid = _insert_tx(db_conn, filing_id=filing_id, asset_raw=asset, source_row=f"r{i}")
        tids.append(tid)
        queue_transaction_review(
            db_conn,
            transaction_id=tid,
            reason="asset_resolution",
            notes="old",
        )

    assert db_conn.execute("SELECT COUNT(*) AS c FROM review_queue").fetchone()["c"] == n

    processed = re_resolve_all_transaction_tickers(db_conn)
    assert processed == n

    assert db_conn.execute("SELECT COUNT(*) AS c FROM review_queue").fetchone()["c"] == 0
    rows = db_conn.execute(
        "SELECT DISTINCT ticker, review_status FROM transactions WHERE id IN ({})".format(
            ",".join(str(t) for t in tids)
        )
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["ticker"] == "EXM"
    assert rows[0]["review_status"] == "exact_match"


def test_re_resolve_non_exact_queues_review_without_per_row_commit(db_conn, monkeypatch: pytest.MonkeyPatch):
    filing_id = _seed_member_and_filing(db_conn)
    asset = "Some issuer line"
    tid = _insert_tx(db_conn, filing_id=filing_id, asset_raw=asset, source_row="a")

    calls: list[bool] = []

    def fake_resolve(conn, a: str, *, commit: bool = True):
        calls.append(commit)
        return {
            "issuer_name": "Some issuer line",
            "ticker": None,
            "sector": "",
            "industry": "",
            "asset_type": "unknown",
            "cusip_or_figi": "",
            "asset_name_normalized": "Some issuer line",
            "confidence_score": 0.5,
            "match_source": "none",
            "review_status": "manual_review",
        }

    monkeypatch.setattr("src.ingest_house.resolve_asset", fake_resolve)

    processed = re_resolve_all_transaction_tickers(db_conn)
    assert processed == 1
    assert calls == [False]

    rq = db_conn.execute(
        "SELECT reason, notes FROM review_queue WHERE transaction_id = ?",
        (tid,),
    ).fetchone()
    assert rq is not None
    assert rq["reason"] == "asset_resolution"
    assert "Some issuer line" in (rq["notes"] or "")

    row = db_conn.execute("SELECT review_status, ticker FROM transactions WHERE id = ?", (tid,)).fetchone()
    assert row["review_status"] == "manual_review"


def test_re_resolve_skips_empty_asset_name(db_conn):
    filing_id = _seed_member_and_filing(db_conn)
    _insert_tx(db_conn, filing_id=filing_id, asset_raw="   ", source_row="empty-asset")
    tid2 = _insert_tx(db_conn, filing_id=filing_id, asset_raw="ValidCo (VCO) [ST]", source_row="ok")

    assert re_resolve_all_transaction_tickers(db_conn) == 1
    v = db_conn.execute("SELECT ticker FROM transactions WHERE id = ?", (tid2,)).fetchone()
    assert v["ticker"] == "VCO"


def test_re_resolve_zero_transactions(db_conn):
    _seed_member_and_filing(db_conn)
    assert re_resolve_all_transaction_tickers(db_conn) == 0


def test_upsert_issuer_commit_false_requires_explicit_commit(tmp_path: Path):
    path = tmp_path / "c.sqlite"
    c1 = get_connection(path)
    init_db(c1)
    upsert_issuer(c1, issuer_name="HoldCo", ticker="HLD", asset_type="equity", commit=False)
    c1.close()

    c2 = get_connection(path)
    init_db(c2)
    assert c2.execute("SELECT COUNT(*) AS c FROM issuers").fetchone()["c"] == 0
    upsert_issuer(c2, issuer_name="HoldCo", ticker="HLD", asset_type="equity", commit=True)
    assert c2.execute("SELECT COUNT(*) AS c FROM issuers").fetchone()["c"] == 1
    c2.close()


def test_re_resolve_bulk_prefetch_env_runs_without_error(db_conn, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CONGRESS_RE_RESOLVE_TICKERS_BULK", "1")
    filing_id = _seed_member_and_filing(db_conn)
    a1 = "Alpha (AAA) [ST]"
    a2 = "Beta (BBB) [ST]"
    _insert_tx(db_conn, filing_id=filing_id, asset_raw=a1, source_row="1")
    _insert_tx(db_conn, filing_id=filing_id, asset_raw=a2, source_row="2")

    n = re_resolve_all_transaction_tickers(db_conn)
    assert n == 2
    tickers = {
        r["ticker"]
        for r in db_conn.execute("SELECT ticker FROM transactions WHERE filing_id = ?", (filing_id,))
    }
    assert tickers == {"AAA", "BBB"}
