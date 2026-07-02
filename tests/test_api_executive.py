"""Smoke + contract tests for the Executive (OGE) router.

Mirrors ``test_api_members.py``: auth gate + payload shape + pagination math.
Seeds a small Executive dataset into a tmp SQLite before each test that needs
data; ``get_connection`` is monkeypatched to read from the tmp DB so the API
sees the seeded rows without touching the real on-disk database.
"""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture
def auth_env(monkeypatch):
    monkeypatch.setenv("APP_USERNAME", "analyst")
    monkeypatch.setenv("APP_PASSWORD", "secret123")
    monkeypatch.setenv("APP_SESSION_SECRET", "test-secret")


@pytest.fixture
def seeded_db(monkeypatch, tmp_path):
    """Create a tmp SQLite, seed Executive rows, point the app at it.

    The seed dataset has:
      * one Executive member (Donald J. Trump)
      * one 278-T filing + 2 transactions
      * one 278e filing + 2 holdings rows
      * one House member/filing/transaction (so we can verify the Executive
        endpoints do NOT leak House data).
    """
    from src import config
    from src import db as db_module
    from src.db import (
        get_connection,
        init_db,
        insert_executive_holding,
        insert_filing,
        insert_transaction,
        upsert_member,
    )

    db_path = tmp_path / "test_executive.sqlite"
    monkeypatch.setattr(config, "DB_PATH", db_path)
    monkeypatch.setattr(db_module, "DB_PATH", db_path)

    conn = get_connection()
    init_db(conn)

    # Executive member
    member_id = upsert_member(conn, full_name="Donald J. Trump", chamber="Executive")

    # House member (for isolation checks)
    upsert_member(conn, full_name="Nancy Pelosi", chamber="House")

    # 278-T filing #1 + 2 transactions (filer/Buy + spouse/Sell)
    periodic_filing_id = insert_filing(
        conn,
        member_id=member_id,
        chamber="Executive",
        filing_type="OGE278T",
        filing_date="2026-02-26",
        doc_id="174165F6E1E120B185258DB000347F54",
        source_url="https://extapps2.oge.gov/201/Presiden.nsf/PAS+Index/.../file.pdf",
        raw_document_path="/tmp/dummy_278t.pdf",
        source_hash="abc123",
    )
    insert_transaction(
        conn,
        filing_id=periodic_filing_id,
        issuer_id=None,
        transaction_date="2026-02-15",
        owner_type="filer",
        asset_name_raw="Apple Inc",
        asset_name_normalized="Apple Inc",
        asset_type="equity",
        ticker="AAPL",
        cusip_or_figi="",
        transaction_type="P (Buy)",
        amount_low=1001,
        amount_high=15000,
        amount_range_raw="$1,001 - $15,000",
        confidence_score=0.99,
        review_status="exact_match",
        source_page=1,
        source_row="0",
        source_hash="txn1",
    )
    insert_transaction(
        conn,
        filing_id=periodic_filing_id,
        issuer_id=None,
        transaction_date="2026-02-16",
        owner_type="spouse",
        asset_name_raw="Microsoft Corp",
        asset_name_normalized="Microsoft Corp",
        asset_type="equity",
        ticker="MSFT",
        cusip_or_figi="",
        transaction_type="S (Sell)",
        amount_low=15001,
        amount_high=50000,
        amount_range_raw="$15,001 - $50,000",
        confidence_score=0.99,
        review_status="exact_match",
        source_page=1,
        source_row="1",
        source_hash="txn2",
    )

    # 278-T filing #2 + 1 transaction (filer/Sell) — lets the filing_doc_id
    # filter demonstrate narrowing from N → 1.
    second_filing_doc_id = "CD75555856A7D2E485258DE4002DD4A0"
    second_periodic_filing_id = insert_filing(
        conn,
        member_id=member_id,
        chamber="Executive",
        filing_type="OGE278T",
        filing_date="2026-03-15",
        doc_id=second_filing_doc_id,
        source_url="https://extapps2.oge.gov/201/Presiden.nsf/PAS+Index/.../second.pdf",
        raw_document_path="/tmp/dummy_278t_b.pdf",
        source_hash="ghi789",
    )
    insert_transaction(
        conn,
        filing_id=second_periodic_filing_id,
        issuer_id=None,
        transaction_date="2026-03-10",
        owner_type="filer",
        asset_name_raw="NVIDIA Corp",
        asset_name_normalized="NVIDIA Corp",
        asset_type="equity",
        ticker="NVDA",
        cusip_or_figi="",
        transaction_type="S (Sell)",
        amount_low=50001,
        amount_high=100000,
        amount_range_raw="$50,001 - $100,000",
        confidence_score=0.99,
        review_status="exact_match",
        source_page=1,
        source_row="0",
        source_hash="txn3",
    )

    # 278e filing + 2 holdings
    annual_filing_id = insert_filing(
        conn,
        member_id=member_id,
        chamber="Executive",
        filing_type="OGE278e",
        filing_date="2025-05-15",
        doc_id="4EC9A8E6DD078F2985258CA9002C9377",
        source_url="https://extapps2.oge.gov/201/Presiden.nsf/PAS+Index/.../annual.pdf",
        raw_document_path="/tmp/dummy_278e.pdf",
        source_hash="def456",
    )
    insert_executive_holding(
        conn,
        filing_id=annual_filing_id,
        asset_name="Apple Inc",
        value_range="$1,001 - $15,000",
        owner_type="filer",
        asset_type="equity",
        source_page=1,
        source_row="0",
        parse_warning=None,
        source_hash="hold1",
    )
    insert_executive_holding(
        conn,
        filing_id=annual_filing_id,
        asset_name="Treasury Note",
        value_range="$15,001 - $50,000",
        owner_type="spouse",
        asset_type="bond",
        source_page=1,
        source_row="1",
        parse_warning=None,
        source_hash="hold2",
    )

    conn.close()
    return db_path


@pytest.fixture
def client(auth_env, seeded_db):
    from src.api import repository

    repository._cache_key = None
    repository._cache_transactions = None
    repository._cache_review = None
    return TestClient(__import__("src.api.app", fromlist=["create_app"]).create_app())


def _login(client: TestClient) -> None:
    assert client.post(
        "/api/login", json={"username": "analyst", "password": "secret123"}
    ).status_code == 200


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #
def test_executive_filers_requires_auth(client):
    assert client.get("/api/executive/filers").status_code == 401


def test_executive_transactions_requires_auth(client):
    assert client.get("/api/executive/transactions").status_code == 401


def test_executive_filings_requires_auth(client):
    assert client.get("/api/executive/filings").status_code == 401


def test_executive_holdings_requires_auth(client):
    assert client.get("/api/executive/holdings").status_code == 401


# --------------------------------------------------------------------------- #
# Filers
# --------------------------------------------------------------------------- #
def test_executive_filers_shape(client):
    _login(client)
    r = client.get("/api/executive/filers")
    assert r.status_code == 200
    data = r.json()
    assert data["ready"] is True
    assert isinstance(data["filers"], list)
    assert data["filers"], "expected at least one filer"
    row = data["filers"][0]
    for key in ("filer_name", "latest_filing_date", "filing_count", "transaction_count"):
        assert key in row, f"missing filers row key: {key}"
    assert row["filer_name"] == "Donald J. Trump"
    assert row["filing_count"] == 3  # 2 OGE278T + 1 OGE278e
    assert row["transaction_count"] == 3


# --------------------------------------------------------------------------- #
# Filings
# --------------------------------------------------------------------------- #
def test_executive_filings_shape(client):
    _login(client)
    r = client.get("/api/executive/filings")
    assert r.status_code == 200
    data = r.json()
    assert data["ready"] is True
    assert isinstance(data["filings"], list)
    by_type = {f["filing_type"]: f for f in data["filings"]}
    assert "OGE278T" in by_type
    assert "OGE278e" in by_type
    # Two OGE278T filings exist (each row in the list is a single filing);
    # the dict comprehension last-write-wins on duplicate filing_type, so the
    # assertion below just checks that *some* OGE278T row exists with the
    # expected URL and that the aggregate transaction_count across both
    # OGE278T filings sums to 3.
    oge278t_rows = [f for f in data["filings"] if f["filing_type"] == "OGE278T"]
    assert len(oge278t_rows) == 2
    assert sum(f["transaction_count"] for f in oge278t_rows) == 3
    assert "extapps2.oge.gov" in oge278t_rows[0]["source_url"]
    assert by_type["OGE278e"]["transaction_count"] == 0


# --------------------------------------------------------------------------- #
# Transactions
# --------------------------------------------------------------------------- #
def test_executive_transactions_shape_and_isolation(client):
    _login(client)
    r = client.get("/api/executive/transactions?page_size=50")
    assert r.status_code == 200
    data = r.json()
    assert data["ready"] is True
    assert data["total"] == 3
    assert all(row["chamber"] == "Executive" for row in data["rows"])
    # No House leak.
    assert all("Nancy Pelosi" not in row["member"] for row in data["rows"])
    # Summary block.
    summary = data["summary"]
    for key in (
        "ready",
        "transaction_count",
        "filer_count",
        "filing_count",
        "buy_count",
        "sell_count",
        "exchange_count",
    ):
        assert key in summary, f"missing summary.{key}"
    assert summary["transaction_count"] == 3
    assert summary["filer_count"] == 1
    # filing_count is derived from the unique `filing_type` column on the
    # filtered transactions; both 278-T rows share the same type, so the
    # distinct count is 1 (pre-existing analytics behavior).
    assert summary["filing_count"] == 1
    assert summary["buy_count"] == 1
    assert summary["sell_count"] == 2
    assert summary["exchange_count"] == 0
    # Owner-type breakdown.
    by_owner = data["by_owner_type"]
    assert by_owner.get("filer", {}).get("count") == 2
    assert by_owner.get("spouse", {}).get("count") == 1


def test_executive_transactions_filter_by_owner_type(client):
    _login(client)
    r = client.get("/api/executive/transactions?owner_type=spouse&page_size=50")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert data["rows"][0]["owner_type"] == "spouse"


def test_executive_transactions_filter_by_transaction_type(client):
    _login(client)
    r = client.get("/api/executive/transactions?transaction_type=P%20%28Buy%29&page_size=50")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert data["rows"][0]["transaction_type"] == "P (Buy)"


def test_executive_transactions_pagination_math(client):
    _login(client)
    page1 = client.get("/api/executive/transactions?page=1&page_size=1").json()
    assert page1["total"] == 3
    assert page1["total_pages"] == 3
    assert len(page1["rows"]) == 1
    page2 = client.get("/api/executive/transactions?page=2&page_size=1").json()
    assert len(page2["rows"]) == 1
    assert page1["rows"][0] != page2["rows"][0]


def test_executive_transactions_filter_by_filing_doc_id(client):
    _login(client)
    doc_id = "CD75555856A7D2E485258DE4002DD4A0"
    r = client.get(
        f"/api/executive/transactions?filing_doc_id={doc_id}&page_size=50"
    )
    assert r.status_code == 200
    data = r.json()
    # Filing #2 only has the NVDA sell row.
    assert data["total"] == 1
    assert data["rows"][0]["doc_id"] == doc_id
    assert data["rows"][0]["ticker"] == "NVDA"


def test_executive_transactions_filing_doc_id_no_match_returns_empty(client):
    _login(client)
    r = client.get(
        "/api/executive/transactions?filing_doc_id=does-not-exist&page_size=50"
    )
    assert r.status_code == 200
    data = r.json()
    assert data["ready"] is False
    assert data["total"] == 0
    assert data["rows"] == []
    assert data["total_pages"] == 0


# --------------------------------------------------------------------------- #
# Holdings
# --------------------------------------------------------------------------- #
def test_executive_holdings_shape(client):
    _login(client)
    r = client.get("/api/executive/holdings")
    assert r.status_code == 200
    data = r.json()
    assert data["ready"] is True
    assert isinstance(data["holdings"], list)
    assert len(data["holdings"]) == 2
    for row in data["holdings"]:
        for key in (
            "filer_name",
            "filing_type",
            "filing_date",
            "asset_name",
            "value_range",
            "owner_type",
            "asset_type",
            "source_url",
        ):
            assert key in row, f"missing holdings row key: {key}"
    # Annual report rows only — no 278-T entries.
    assert all(h["filing_type"] == "OGE278e" for h in data["holdings"])