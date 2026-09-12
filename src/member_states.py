"""State (and party) for members created by PTR ingest.

A PTR PDF names the filer but not the state, so PTR ingest used to upsert the
member with ``state=''``. Every trade hangs off those rows, which is why alert
headings and the dashboard showed "Rep. Kelly Louise Morrison" with no
"(D-MN)": no state means the party matcher's last-name fallback can't run
either.

The state is recoverable. House PTRs share their ``doc_id`` with a row of the
FD metadata index (``fd_filings.state_district``); Senate PTRs have no such
row, so the congress-legislators map supplies it by name.

The district is deliberately left blank: members are unique on
``(normalized_name, chamber, state, district)``, and one PTR row spans every
district a member has held (Pelosi CA-11 then CA-12).
"""
from __future__ import annotations

import sqlite3
from collections import Counter
from typing import Any

from .member_parties import get_party_lookup, match_party, match_state
from .utils import normalize_whitespace, split_state_district

_CONGRESS_CHAMBERS = ("House", "Senate")


def fd_state_for_doc(conn: sqlite3.Connection, chamber: str, doc_id: str | None) -> str:
    """State from the FD metadata row sharing this ``doc_id`` ('' if none)."""
    doc = normalize_whitespace(doc_id or "")
    if not doc:
        return ""
    row = conn.execute(
        """
        SELECT state_district
        FROM fd_filings
        WHERE chamber = ? AND doc_id = ? AND COALESCE(state_district, '') <> ''
        ORDER BY id DESC
        LIMIT 1
        """,
        (chamber, doc),
    ).fetchone()
    return split_state_district(row[0])[0] if row else ""


def ptr_member_state_and_party(
    conn: sqlite3.Connection,
    *,
    full_name: str,
    chamber: str,
    doc_id: str | None,
    lookup: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """``(state, party)`` to store on a member created from a PTR."""
    lookup = lookup if lookup is not None else get_party_lookup()
    state = fd_state_for_doc(conn, chamber, doc_id) or match_state(
        full_name, chamber=chamber, lookup=lookup
    )
    party = match_party(full_name, chamber=chamber, state=state, lookup=lookup)
    return state, party


def _state_from_filings(conn: sqlite3.Connection, member_id: int, chamber: str) -> str | None:
    """Unanimous FD state across the member's filings; None when they disagree."""
    states = Counter(
        split_state_district(row[0])[0]
        for row in conn.execute(
            """
            SELECT fd.state_district
            FROM filings f
            JOIN fd_filings fd ON fd.doc_id = f.doc_id AND fd.chamber = f.chamber
            WHERE f.member_id = ? AND f.chamber = ? AND COALESCE(fd.state_district, '') <> ''
            """,
            (member_id, chamber),
        )
    )
    if len(states) > 1:
        return None
    return next(iter(states), "")


def move_filings(conn: sqlite3.Connection, source_id: int, target_id: int) -> int:
    """Re-point filings; returns how many stayed behind on a uniqueness clash."""
    stuck = 0
    for (filing_id,) in conn.execute(
        "SELECT id FROM filings WHERE member_id = ?", (source_id,)
    ).fetchall():
        try:
            conn.execute(
                "UPDATE filings SET member_id = ?, updated_at = datetime('now') WHERE id = ?",
                (target_id, filing_id),
            )
        except sqlite3.IntegrityError:
            stuck += 1
    return stuck


def backfill_member_states(
    conn: sqlite3.Connection,
    *,
    lookup: dict[str, Any] | None = None,
) -> dict[str, int]:
    """Give stateless House/Senate members a state, then a party if still blank.

    Idempotent: only rows with ``state = ''`` are considered. When the stated
    row already exists (same name, chamber, state, blank district) the filings
    move onto it and the empty stateless row is deleted.
    """
    lookup = lookup if lookup is not None else get_party_lookup()
    rows = conn.execute(
        f"""
        SELECT id, full_name, normalized_name, chamber, district, party
        FROM members
        WHERE state = '' AND chamber IN ({", ".join("?" for _ in _CONGRESS_CHAMBERS)})
        ORDER BY id
        """,
        _CONGRESS_CHAMBERS,
    ).fetchall()

    stats = {"candidates": len(rows), "updated": 0, "merged": 0, "parties": 0, "unresolved": 0}
    for row in rows:
        member_id = int(row["id"])
        chamber = row["chamber"]
        state = _state_from_filings(conn, member_id, chamber)
        if state is None:
            stats["unresolved"] += 1
            continue
        state = state or match_state(row["full_name"], chamber=chamber, lookup=lookup)
        if not state:
            stats["unresolved"] += 1
            continue

        twin = conn.execute(
            """
            SELECT id, party FROM members
            WHERE normalized_name = ? AND chamber = ? AND state = ? AND district = ?
            """,
            (row["normalized_name"], chamber, state, row["district"]),
        ).fetchone()
        if twin is not None:
            target_id = int(twin["id"])
            if move_filings(conn, member_id, target_id) == 0:
                conn.execute("DELETE FROM members WHERE id = ?", (member_id,))
            stats["merged"] += 1
            party = (twin["party"] or "").strip()
        else:
            target_id = member_id
            conn.execute(
                "UPDATE members SET state = ?, updated_at = datetime('now') WHERE id = ?",
                (state, member_id),
            )
            stats["updated"] += 1
            party = (row["party"] or "").strip()

        if not party:
            party = match_party(row["full_name"], chamber=chamber, state=state, lookup=lookup)
            if party:
                conn.execute(
                    "UPDATE members SET party = ?, updated_at = datetime('now') WHERE id = ?",
                    (party, target_id),
                )
                stats["parties"] += 1

    conn.commit()
    return stats
