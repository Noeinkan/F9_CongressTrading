"""Contract tests for the Senate router and its analytics.

The router reuses the Home summary on the Senate slice, so these tests check
the two things that are the Senate page's own: that House rows never leak in,
and the timeliness / filings figures computed on top.
"""
from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src.api._senate_analytics import filing_list, filing_timeliness, senate_rows


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture
def auth_env(monkeypatch):
    monkeypatch.setenv("APP_USERNAME", "analyst")
    monkeypatch.setenv("APP_PASSWORD", "secret123")
    monkeypatch.setenv("APP_SESSION_SECRET", "test-secret")


def _seed(conn, *, member, chamber, doc_id, filing_date, trades, state="CA", party="D"):
    from src.db import insert_filing, insert_transaction, upsert_member

    member_id = upsert_member(conn, full_name=member, chamber=chamber, state=state, party=party)
    filing_id = insert_filing(
        conn,
        member_id=member_id,
        chamber=chamber,
        filing_type="PTR",
        filing_date=filing_date,
        doc_id=doc_id,
        source_url="",
        raw_document_path=f"/tmp/{doc_id}.html",
        source_hash=f"f-{doc_id}",
    )
    for i, (traded, ticker, tx_type, low, high) in enumerate(trades):
        insert_transaction(
            conn,
            filing_id=filing_id,
            issuer_id=None,
            transaction_date=traded,
            owner_type="self",
            asset_name_raw=f"{ticker} Common Stock",
            asset_name_normalized=ticker.lower(),
            asset_type="stock",
            ticker=ticker,
            cusip_or_figi="",
            transaction_type=tx_type,
            amount_low=low,
            amount_high=high,
            amount_range_raw=f"${low:,} - ${high:,}",
            confidence_score=0.99,
            review_status="exact_match",
            source_page=1,
            source_row=str(i),
            source_hash=f"t-{doc_id}-{i}",
        )


def _point_app_at(monkeypatch, db_path):
    from src import config
    from src import db as db_module

    monkeypatch.setattr(config, "DB_PATH", db_path)
    monkeypatch.setattr(db_module, "DB_PATH", db_path)


@pytest.fixture
def seeded_db(monkeypatch, tmp_path):
    """Two senators (one files late) and one House member who must not leak in."""
    from src.db import get_connection, init_db

    db_path = tmp_path / "test_senate.sqlite"
    _point_app_at(monkeypatch, db_path)
    conn = get_connection()
    init_db(conn)
    _seed(
        conn, member="John R Curtis", chamber="Senate", doc_id="sen-1",
        filing_date="2026-06-30", state="UT", party="R",
        trades=[
            ("2026-06-10", "AAPL", "Purchase", 1001, 15000),
            ("2026-03-01", "MSFT", "Sale (Full)", 15001, 50000),  # 121 days: late
        ],
    )
    _seed(
        conn, member="Gary C Peters", chamber="Senate", doc_id="sen-2",
        filing_date="2026-07-02", state="MI", party="D",
        trades=[("2026-06-20", "NVDA", "Purchase", 50001, 100000)],
    )
    _seed(
        conn, member="Nancy Pelosi", chamber="House", doc_id="house-1",
        filing_date="2026-07-01",
        trades=[("2026-06-15", "TSLA", "P", 1000001, 5000000)],
    )
    conn.close()
    return db_path


def _client() -> TestClient:
    from src.api import repository
    from src.api.app import create_app

    repository._cache_key = None
    repository._cache_transactions = None
    repository._cache_review = None
    return TestClient(create_app())


def _login(client: TestClient) -> None:
    assert client.post(
        "/api/login", json={"username": "analyst", "password": "secret123"}
    ).status_code == 200


# --------------------------------------------------------------------------- #
# Router
# --------------------------------------------------------------------------- #
def test_senate_summary_requires_auth(auth_env, seeded_db):
    assert _client().get("/api/senate/summary").status_code == 401


def test_senate_summary_holds_only_senate_rows(auth_env, seeded_db):
    client = _client()
    _login(client)
    body = client.get("/api/senate/summary").json()

    assert body["ready"] is True
    assert body["senate_rows_all_time"] == 3
    assert body["hero"]["total_transactions"] == 3
    assert body["hero"]["total_members"] == 2
    assert body["hero"]["active_chambers"] == "Senate"
    members = {row["member"] for row in body["members_leaderboard"]}
    assert members == {"John R Curtis", "Gary C Peters"}
    assert all(row["chamber"] == "Senate" for row in body["latest_transactions"])
    assert "TSLA" not in {row["ticker"] for row in body["latest_transactions"]}

    assert body["coverage"] == {
        "senators": 2,
        "filings": 2,
        "first_filing": "2026-06-30",
        "latest_filing": "2026-07-02",
    }
    assert body["timeliness"]["late_trades"] == 1
    assert body["timeliness"]["late_filers"][0]["member"] == "John R Curtis"
    assert [f["doc_id"] for f in body["filings"]] == ["sen-2", "sen-1"]


def test_senate_summary_without_senate_rows_is_empty_not_an_error(
    auth_env, monkeypatch, tmp_path
):
    from src.db import get_connection, init_db

    db_path = tmp_path / "house_only.sqlite"
    _point_app_at(monkeypatch, db_path)
    conn = get_connection()
    init_db(conn)
    _seed(
        conn, member="Nancy Pelosi", chamber="House", doc_id="house-1",
        filing_date="2026-07-01", trades=[("2026-06-15", "TSLA", "P", 1001, 15000)],
    )
    conn.close()

    client = _client()
    _login(client)
    response = client.get("/api/senate/summary")
    assert response.status_code == 200
    body = response.json()
    assert body["senate_rows_all_time"] == 0
    assert body["hero"]["total_transactions"] == 0
    assert body["filings"] == []
    assert body["timeliness"]["dated_trades"] == 0


# --------------------------------------------------------------------------- #
# Analytics
# --------------------------------------------------------------------------- #
def _frame(*rows: dict) -> pd.DataFrame:
    base = {
        "member": "Sen. A",
        "chamber": "Senate",
        "party": "R",
        "state": "UT",
        "doc_id": "d1",
        "ticker": "AAPL",
        "amount_low": 1001.0,
        "amount_high": 15000.0,
        "filing_date": pd.Timestamp("2026-06-30"),
        "transaction_date": pd.Timestamp("2026-06-10"),
    }
    return pd.DataFrame([{**base, **r} for r in rows])


def test_senate_rows_ignores_case_and_whitespace():
    frame = _frame({"chamber": " senate "}, {"chamber": "House"}, {"chamber": "SENATE"})
    assert len(senate_rows(frame)) == 2


def test_timeliness_counts_days_past_the_deadline_not_the_raw_delay():
    frame = _frame(
        {"transaction_date": pd.Timestamp("2026-06-10")},  # 20 days
        {"transaction_date": pd.Timestamp("2026-03-01")},  # 121 days → 76 late
        {"transaction_date": pd.NaT},  # undatable: not counted
    )
    result = filing_timeliness(frame)
    assert result["dated_trades"] == 2
    assert result["late_trades"] == 1
    assert result["late_share_label"] == "50%"
    assert result["late_filers"] == [
        {"member": "Sen. A", "trades": 2, "late_trades": 1, "worst_days_late": 76}
    ]


def test_filing_list_groups_rows_by_document():
    frame = _frame(
        {"doc_id": "d1", "ticker": "AAPL"},
        {"doc_id": "d1", "ticker": "MSFT", "amount_low": 15001.0, "amount_high": 50000.0},
        {"doc_id": "d2", "ticker": "", "filing_date": pd.Timestamp("2026-07-02")},
    )
    filings = filing_list(frame)
    assert [f["doc_id"] for f in filings] == ["d2", "d1"]
    assert filings[1]["trades"] == 2
    assert filings[1]["tickers"] == 2
    assert filings[0]["tickers"] == 0
    assert filings[1]["amount_low"] == 16002.0
    assert filings[1]["party"] == "Republican"
