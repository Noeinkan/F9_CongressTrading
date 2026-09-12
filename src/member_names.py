"""Names for House PTR filers whose PDF header could not be read.

When the parser finds no filer name (scanned or hand-filled PDFs), ingest used
to fall back to the PDF's file name, i.e. the document number, and created a
member called "8220731". The FD metadata index already knows who filed that
document (``fd_filings.member`` for the same ``doc_id``), so that name is used
instead, and existing doc-number members are renamed by moving their filings.
"""
from __future__ import annotations

import sqlite3
from typing import Any

from .db import upsert_member
from .member_parties import disclosure_name_key, get_party_lookup
from .member_states import move_filings, ptr_member_state_and_party
from .utils import normalize_whitespace


def fd_member_for_doc(conn: sqlite3.Connection, chamber: str, doc_id: str | None) -> str:
    """Filer name from the FD metadata row sharing this ``doc_id`` ('' if none)."""
    doc = normalize_whitespace(doc_id or "")
    if not doc:
        return ""
    row = conn.execute(
        """
        SELECT member FROM fd_filings
        WHERE chamber = ? AND doc_id = ? AND COALESCE(member, '') <> ''
        ORDER BY id DESC
        LIMIT 1
        """,
        (chamber, doc),
    ).fetchone()
    return normalize_whitespace(row[0]) if row else ""


def existing_ptr_member_name(conn: sqlite3.Connection, name: str, *, chamber: str, state: str) -> str:
    """Spelling already used by this filer's other PTRs, so trades stay under one name.

    FD metadata writes "Kelly Louise Morrison" one year and "Hon. Kelly Louise
    Morrison" the next; PTR rows use whichever the PDF header said. Matching on
    the title-free key within the same chamber and state avoids a second member.
    """
    key = disclosure_name_key(name)
    if not key:
        return name
    for row in conn.execute(
        "SELECT full_name FROM members WHERE chamber = ? AND state = ? AND district = '' ORDER BY id",
        (chamber, state),
    ):
        if not row[0].isdigit() and disclosure_name_key(row[0]) == key:
            return row[0]
    return name


def rename_doc_number_members(
    conn: sqlite3.Connection,
    *,
    lookup: dict[str, Any] | None = None,
) -> dict[str, int]:
    """Move filings off House members named after a document number.

    Idempotent: once a doc-number member has no filings left it is deleted, so
    the next run finds nothing.
    """
    lookup = lookup if lookup is not None else get_party_lookup()
    members = conn.execute(
        "SELECT id, full_name FROM members WHERE chamber = 'House' ORDER BY id"
    ).fetchall()
    stats = {"candidates": 0, "renamed": 0, "unresolved": 0}
    for member in members:
        old_name = member["full_name"]
        if not old_name.isdigit():
            continue
        stats["candidates"] += 1
        member_id = int(member["id"])
        fd_name = fd_member_for_doc(conn, "House", old_name)
        if not fd_name:
            stats["unresolved"] += 1
            continue
        state, party = ptr_member_state_and_party(
            conn, full_name=fd_name, chamber="House", doc_id=old_name, lookup=lookup
        )
        name = existing_ptr_member_name(conn, fd_name, chamber="House", state=state)
        target_id = upsert_member(conn, full_name=name, chamber="House", state=state, party=party)
        if move_filings(conn, member_id, target_id):
            stats["unresolved"] += 1
            continue
        conn.execute(
            "UPDATE trades SET member = ? WHERE chamber = 'House' AND member = ?",
            (name, old_name),
        )
        conn.execute("DELETE FROM members WHERE id = ?", (member_id,))
        stats["renamed"] += 1
    conn.commit()
    return stats
