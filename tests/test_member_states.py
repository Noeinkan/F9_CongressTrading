"""State backfill for members created by PTR ingest (src/member_states.py)."""
from __future__ import annotations

import sqlite3

import pytest

from src.db import init_db, insert_fd_filings, insert_filing, upsert_member
from src.member_parties import _build_lookup_indexes
from src.member_states import backfill_member_states, fd_state_for_doc, ptr_member_state_and_party

_LOOKUP = _build_lookup_indexes(
    [
        {"official_full": "Kelly Morrison", "first": "Kelly", "last": "Morrison",
         "party": "Democrat", "chamber": "House", "state": "MN"},
        {"official_full": "Gary C. Peters", "first": "Gary", "last": "Peters",
         "party": "Democrat", "chamber": "Senate", "state": "MI"},
    ]
)


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    init_db(connection)
    yield connection
    connection.close()


def _fd_row(doc_id: str, state_district: str, member: str = "Kelly Louise Morrison") -> dict:
    return {
        "member": member,
        "chamber": "House",
        "filing_type": "P",
        "state_district": state_district,
        "year": 2026,
        "filing_date": "2026-08-01",
        "doc_id": doc_id,
        "source_file": "2026FD.xml",
    }


def _ptr_filing(conn, member_id: int, doc_id: str, chamber: str = "House") -> int:
    return insert_filing(
        conn,
        member_id=member_id,
        chamber=chamber,
        filing_type="PTR",
        filing_date="2026-08-01",
        doc_id=doc_id,
        source_url="",
        raw_document_path=f"{doc_id}.pdf",
        source_hash=doc_id,
    )


def _member(conn, member_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM members WHERE id = ?", (member_id,)).fetchone()


def test_fd_state_for_doc_reads_fd_metadata(conn):
    insert_fd_filings(conn, [_fd_row("20031234", "MN03")])
    assert fd_state_for_doc(conn, "House", "20031234") == "MN"
    assert fd_state_for_doc(conn, "House", "missing") == ""
    assert fd_state_for_doc(conn, "Senate", "20031234") == ""


def test_backfill_fills_state_from_fd_metadata_then_party(conn):
    insert_fd_filings(conn, [_fd_row("20031234", "MN03")])
    member_id = upsert_member(conn, full_name="Hon. Kelly Louise Morrison", chamber="House")
    _ptr_filing(conn, member_id, "20031234")

    stats = backfill_member_states(conn, lookup=_LOOKUP)

    row = _member(conn, member_id)
    assert (row["state"], row["district"], row["party"]) == ("MN", "", "Democrat")
    assert stats["updated"] == 1 and stats["parties"] == 1
    # Idempotent: the row is no longer stateless.
    assert backfill_member_states(conn, lookup=_LOOKUP)["candidates"] == 0


def test_backfill_falls_back_to_legislators_map_for_senate(conn):
    member_id = upsert_member(conn, full_name="Gary C Peters", chamber="Senate")
    _ptr_filing(conn, member_id, "uuid-1", chamber="Senate")

    backfill_member_states(conn, lookup=_LOOKUP)

    row = _member(conn, member_id)
    assert (row["state"], row["party"]) == ("MI", "Democrat")


def test_backfill_merges_into_existing_stated_row(conn):
    insert_fd_filings(conn, [_fd_row("20031234", "MN03")])
    stated_id = upsert_member(conn, full_name="Hon. Kelly Louise Morrison", chamber="House", state="MN")
    stateless_id = upsert_member(conn, full_name="Hon. Kelly Louise Morrison", chamber="House")
    filing_id = _ptr_filing(conn, stateless_id, "20031234")

    stats = backfill_member_states(conn, lookup=_LOOKUP)

    assert stats["merged"] == 1
    assert _member(conn, stateless_id) is None
    moved = conn.execute("SELECT member_id FROM filings WHERE id = ?", (filing_id,)).fetchone()
    assert moved["member_id"] == stated_id
    assert _member(conn, stated_id)["party"] == "Democrat"


def test_backfill_skips_members_whose_filings_disagree_on_state(conn):
    insert_fd_filings(conn, [_fd_row("A1", "MN03"), _fd_row("A2", "TX07")])
    member_id = upsert_member(conn, full_name="Hon. Kelly Louise Morrison", chamber="House")
    _ptr_filing(conn, member_id, "A1")
    _ptr_filing(conn, member_id, "A2")

    stats = backfill_member_states(conn, lookup=_LOOKUP)

    assert stats["unresolved"] == 1
    assert _member(conn, member_id)["state"] == ""


def test_ptr_member_state_and_party_at_ingest(conn):
    insert_fd_filings(conn, [_fd_row("20031234", "MN03")])
    assert ptr_member_state_and_party(
        conn, full_name="Hon. Kelly Louise Morrison", chamber="House", doc_id="20031234", lookup=_LOOKUP
    ) == ("MN", "Democrat")
    # A filer nobody knows: nothing invented.
    assert ptr_member_state_and_party(
        conn, full_name="8220731", chamber="House", doc_id="8220731", lookup=_LOOKUP
    ) == ("", "")
