"""Doc-number member names replaced by the FD metadata filer name (src/member_names.py)."""
from __future__ import annotations

import sqlite3

import pytest

from src.db import init_db, insert_fd_filings, insert_filing, upsert_member
from src.member_names import (
    existing_ptr_member_name,
    fd_member_for_doc,
    rename_doc_number_members,
)
from src.member_parties import _build_lookup_indexes

_LOOKUP = _build_lookup_indexes(
    [
        {"official_full": "Keith Self", "first": "Keith", "last": "Self",
         "party": "Republican", "chamber": "House", "state": "TX"},
    ]
)


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    init_db(connection)
    yield connection
    connection.close()


def _fd(conn, doc_id: str, member: str, state_district: str = "TX03") -> None:
    insert_fd_filings(
        conn,
        [{
            "member": member, "chamber": "House", "filing_type": "P",
            "state_district": state_district, "year": 2026,
            "filing_date": "2026-08-01", "doc_id": doc_id, "source_file": "2026FD.xml",
        }],
    )


def _ptr(conn, member_id: int, doc_id: str) -> int:
    return insert_filing(
        conn, member_id=member_id, chamber="House", filing_type="PTR",
        filing_date="2026-08-01", doc_id=doc_id, source_url="",
        raw_document_path=f"{doc_id}.pdf", source_hash=doc_id,
    )


def test_fd_member_for_doc(conn):
    _fd(conn, "8220731", "Hon. Keith Alan Self")
    assert fd_member_for_doc(conn, "House", "8220731") == "Hon. Keith Alan Self"
    assert fd_member_for_doc(conn, "House", "missing") == ""


def test_existing_ptr_member_name_reuses_spelling_without_title(conn):
    upsert_member(conn, full_name="Hon. Keith Alan Self", chamber="House", state="TX")
    assert existing_ptr_member_name(conn, "Keith Alan Self", chamber="House", state="TX") == "Hon. Keith Alan Self"
    # Other state: a different person, keep the name as given.
    assert existing_ptr_member_name(conn, "Keith Alan Self", chamber="House", state="OH") == "Keith Alan Self"


def test_rename_moves_filing_to_named_member_and_drops_doc_number_row(conn):
    _fd(conn, "8220731", "Hon. Keith Alan Self")
    doc_member = upsert_member(conn, full_name="8220731", chamber="House", state="TX")
    filing_id = _ptr(conn, doc_member, "8220731")

    stats = rename_doc_number_members(conn, lookup=_LOOKUP)

    assert stats == {"candidates": 1, "renamed": 1, "unresolved": 0}
    assert conn.execute("SELECT 1 FROM members WHERE id = ?", (doc_member,)).fetchone() is None
    owner = conn.execute(
        "SELECT m.full_name, m.state, m.party FROM filings f JOIN members m ON m.id = f.member_id WHERE f.id = ?",
        (filing_id,),
    ).fetchone()
    assert tuple(owner) == ("Hon. Keith Alan Self", "TX", "Republican")
    assert rename_doc_number_members(conn, lookup=_LOOKUP)["candidates"] == 0


def test_rename_joins_the_filers_existing_ptr_member(conn):
    _fd(conn, "8220731", "Keith Alan Self")
    named = upsert_member(conn, full_name="Hon. Keith Alan Self", chamber="House", state="TX")
    _ptr(conn, named, "20020001")
    doc_member = upsert_member(conn, full_name="8220731", chamber="House")
    filing_id = _ptr(conn, doc_member, "8220731")

    rename_doc_number_members(conn, lookup=_LOOKUP)

    assert conn.execute("SELECT member_id FROM filings WHERE id = ?", (filing_id,)).fetchone()[0] == named


def test_rename_leaves_member_when_fd_metadata_has_no_name(conn):
    doc_member = upsert_member(conn, full_name="8220999", chamber="House")
    _ptr(conn, doc_member, "8220999")

    stats = rename_doc_number_members(conn, lookup=_LOOKUP)

    assert stats["unresolved"] == 1
    assert conn.execute("SELECT 1 FROM members WHERE id = ?", (doc_member,)).fetchone() is not None
