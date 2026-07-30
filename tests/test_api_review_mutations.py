"""Tests for Review Queue triage mutations (resolve / accept / dismiss)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def auth_env(monkeypatch):
    monkeypatch.setenv("APP_USERNAME", "analyst")
    monkeypatch.setenv("APP_PASSWORD", "secret123")
    monkeypatch.setenv("APP_SESSION_SECRET", "test-secret")


@pytest.fixture
def seeded_review_db(monkeypatch, tmp_path):
    """Seed two open review-queue rows that share an asset name (+ one unique)."""
    from src import config
    from src import db as db_module
    from src.api import repository as repo
    from src.db import (
        get_connection,
        init_db,
        insert_filing,
        insert_transaction,
        queue_transaction_review,
        upsert_member,
    )

    db_path = tmp_path / "test_review.sqlite"
    monkeypatch.setattr(config, "DB_PATH", db_path)
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    monkeypatch.setattr(repo, "DB_PATH", db_path)
    repo.invalidate_data_cache()

    conn = get_connection()
    init_db(conn)
    member_id = upsert_member(conn, full_name="Hon. Test Member", chamber="House", state="NE")
    filing_id = insert_filing(
        conn,
        member_id=member_id,
        chamber="House",
        filing_type="PTR",
        filing_date="2024-06-15",
        doc_id="doc-1",
        source_url="",
        raw_document_path="/tmp/test.pdf",
        source_hash="filing-hash",
    )

    fuzzy_id = insert_transaction(
        conn,
        filing_id=filing_id,
        issuer_id=None,
        transaction_date="2024-06-01",
        owner_type="filer",
        asset_name_raw="Apple Inc (AAPL)",
        asset_name_normalized="Apple Inc",
        asset_type="stock",
        ticker="AAPL",
        cusip_or_figi="",
        transaction_type="P",
        amount_low=1001,
        amount_high=15000,
        amount_range_raw="$1,001 - $15,000",
        confidence_score=0.9,
        review_status="fuzzy_match",
        source_page=1,
        source_row="0",
        source_hash="tx-fuzzy",
    )
    sibling_id = insert_transaction(
        conn,
        filing_id=filing_id,
        issuer_id=None,
        transaction_date="2024-06-02",
        owner_type="filer",
        asset_name_raw="Apple Inc (AAPL)",
        asset_name_normalized="Apple Inc",
        asset_type="stock",
        ticker="AAPL",
        cusip_or_figi="",
        transaction_type="S",
        amount_low=1001,
        amount_high=15000,
        amount_range_raw="$1,001 - $15,000",
        confidence_score=0.88,
        review_status="fuzzy_match",
        source_page=1,
        source_row="1",
        source_hash="tx-sibling",
    )
    manual_id = insert_transaction(
        conn,
        filing_id=filing_id,
        issuer_id=None,
        transaction_date="2024-06-03",
        owner_type="filer",
        asset_name_raw="Some Private Fund LLC",
        asset_name_normalized="Some Private Fund LLC",
        asset_type="other",
        ticker="",
        cusip_or_figi="",
        transaction_type="P",
        amount_low=15001,
        amount_high=50000,
        amount_range_raw="$15,001 - $50,000",
        confidence_score=0.0,
        review_status="manual_review",
        source_page=1,
        source_row="2",
        source_hash="tx-manual",
    )

    for tid in (fuzzy_id, sibling_id, manual_id):
        queue_transaction_review(
            conn,
            transaction_id=tid,
            reason="asset_resolution",
            notes="test",
        )
    conn.close()
    repo.invalidate_data_cache()

    return {
        "fuzzy_id": fuzzy_id,
        "sibling_id": sibling_id,
        "manual_id": manual_id,
        "db_path": db_path,
    }


@pytest.fixture
def client(auth_env, seeded_review_db):
    from src.api.app import create_app

    return TestClient(create_app()), seeded_review_db


def _login(client: TestClient) -> None:
    assert client.post(
        "/api/login", json={"username": "analyst", "password": "secret123"}
    ).status_code == 200


def test_review_mutations_require_auth(client):
    http, ids = client
    assert http.post(f"/api/review/items/{ids['fuzzy_id']}/dismiss").status_code == 401
    assert http.post(
        f"/api/review/items/{ids['fuzzy_id']}/resolve", json={"ticker": "AAPL"}
    ).status_code == 401


def test_review_summary_includes_transaction_id(client):
    http, _ids = client
    _login(http)
    data = http.get("/api/review/summary").json()
    assert data["ready"] is True
    assert data["total"] == 3
    assert all(row.get("transaction_id") for row in data["rows"])


def test_accept_promotes_fuzzy_ticker(client):
    http, ids = client
    _login(http)
    r = http.post(f"/api/review/items/{ids['fuzzy_id']}/accept", json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["action"] == "accept"
    assert body["ticker"] == "AAPL"

    from src.db import get_connection

    conn = get_connection()
    try:
        tx = conn.execute(
            "SELECT ticker, review_status, confidence_score FROM transactions WHERE id = ?",
            (ids["fuzzy_id"],),
        ).fetchone()
        queued = conn.execute(
            "SELECT 1 FROM review_queue WHERE transaction_id = ?",
            (ids["fuzzy_id"],),
        ).fetchone()
    finally:
        conn.close()

    assert tx["ticker"] == "AAPL"
    assert tx["review_status"] == "exact_match"
    assert float(tx["confidence_score"]) == 1.0
    assert queued is None

    summary = http.get("/api/review/summary").json()
    assert summary["total"] == 2


def test_resolve_sets_ticker_and_apply_to_asset(client):
    http, ids = client
    _login(http)
    r = http.post(
        f"/api/review/items/{ids['fuzzy_id']}/resolve",
        json={"ticker": "AAPL", "apply_to_asset": True},
    )
    assert r.status_code == 200, r.text
    assert r.json()["updated_count"] == 2

    from src.db import get_connection

    conn = get_connection()
    try:
        for tid in (ids["fuzzy_id"], ids["sibling_id"]):
            tx = conn.execute(
                "SELECT review_status FROM transactions WHERE id = ?",
                (tid,),
            ).fetchone()
            assert tx["review_status"] == "exact_match"
            assert (
                conn.execute(
                    "SELECT 1 FROM review_queue WHERE transaction_id = ?",
                    (tid,),
                ).fetchone()
                is None
            )
        # Unique asset left alone
        assert (
            conn.execute(
                "SELECT 1 FROM review_queue WHERE transaction_id = ?",
                (ids["manual_id"],),
            ).fetchone()
            is not None
        )
        cached = conn.execute(
            "SELECT ticker, resolution_status, match_source FROM asset_resolution_cache "
            "WHERE asset_name_raw = ?",
            ("Apple Inc (AAPL)",),
        ).fetchone()
    finally:
        conn.close()

    assert cached is not None
    assert cached["ticker"] == "AAPL"
    assert cached["resolution_status"] == "exact_match"
    assert cached["match_source"] == "manual_review"


def test_resolve_manual_ticker(client):
    http, ids = client
    _login(http)
    r = http.post(
        f"/api/review/items/{ids['manual_id']}/resolve",
        json={"ticker": "XYZ"},
    )
    assert r.status_code == 200, r.text
    from src.db import get_connection

    conn = get_connection()
    try:
        tx = conn.execute(
            "SELECT ticker, review_status FROM transactions WHERE id = ?",
            (ids["manual_id"],),
        ).fetchone()
    finally:
        conn.close()
    assert tx["ticker"] == "XYZ"
    assert tx["review_status"] == "exact_match"


def test_resolve_rejects_bad_ticker(client):
    http, ids = client
    _login(http)
    r = http.post(
        f"/api/review/items/{ids['manual_id']}/resolve",
        json={"ticker": "not a ticker!!!"},
    )
    assert r.status_code == 400


def test_accept_without_ticker_fails(client):
    http, ids = client
    _login(http)
    r = http.post(f"/api/review/items/{ids['manual_id']}/accept", json={})
    assert r.status_code == 400


def test_dismiss_removes_queue_row_keeps_transaction(client):
    http, ids = client
    _login(http)
    r = http.post(f"/api/review/items/{ids['manual_id']}/dismiss")
    assert r.status_code == 200, r.text

    from src.db import get_connection

    conn = get_connection()
    try:
        tx = conn.execute(
            "SELECT ticker, review_status FROM transactions WHERE id = ?",
            (ids["manual_id"],),
        ).fetchone()
        queued = conn.execute(
            "SELECT 1 FROM review_queue WHERE transaction_id = ?",
            (ids["manual_id"],),
        ).fetchone()
    finally:
        conn.close()

    assert tx["ticker"] == ""
    assert tx["review_status"] == "manual_review"
    assert queued is None
    assert http.get("/api/review/summary").json()["total"] == 2


def test_dismiss_missing_returns_404(client):
    http, _ids = client
    _login(http)
    assert http.post("/api/review/items/999999/dismiss").status_code == 404
