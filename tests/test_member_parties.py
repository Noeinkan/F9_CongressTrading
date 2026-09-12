"""Tests for member party enrichment (congress-legislators map)."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from src.api._patterns_analytics import bipartisan_tickers
from src.db import init_db, upsert_member
from src.member_parties import (
    backfill_member_parties,
    build_legislators_payload,
    disclosure_name_key,
    legislator_record_from_yaml,
    load_legislators_parties,
    match_party,
    match_state,
    strip_honorifics,
    write_legislators_parties_json,
)


def test_strip_honorifics():
    assert strip_honorifics("Hon. Pete Aguilar") == "Pete Aguilar"
    assert strip_honorifics("Dr. Jay Thomas Allen") == "Jay Thomas Allen"
    assert strip_honorifics("Ms. Lynn Ann Afendoulis") == "Lynn Ann Afendoulis"
    assert strip_honorifics("The Honorable Nancy Pelosi") == "Nancy Pelosi"
    assert strip_honorifics("Pete Aguilar") == "Pete Aguilar"


def test_disclosure_name_key_strips_hon():
    assert disclosure_name_key("Hon. Pete Aguilar") == disclosure_name_key("Pete Aguilar")


def test_legislator_record_from_yaml_current():
    entry = {
        "name": {"first": "Pete", "last": "Aguilar", "official_full": "Pete Aguilar"},
        "terms": [
            {
                "type": "rep",
                "start": "2015-01-06",
                "end": "2027-01-03",
                "state": "CA",
                "party": "Democrat",
            }
        ],
    }
    rec = legislator_record_from_yaml(entry, require_recent=False)
    assert rec is not None
    assert rec["party"] == "Democrat"
    assert rec["chamber"] == "House"
    assert rec["state"] == "CA"


def test_legislator_record_skips_old_historical():
    entry = {
        "name": {"first": "Old", "last": "Member", "official_full": "Old Member"},
        "terms": [
            {
                "type": "rep",
                "start": "1990-01-03",
                "end": "1995-01-03",
                "state": "NY",
                "party": "Democrat",
            }
        ],
    }
    assert legislator_record_from_yaml(entry, require_recent=True) is None


def test_match_party_exact_and_honorific(tmp_path: Path):
    payload = {
        "meta": {"source": "test", "updated": "2026-01-01", "count": 1},
        "legislators": [
            {
                "official_full": "Pete Aguilar",
                "first": "Pete",
                "last": "Aguilar",
                "party": "Democrat",
                "chamber": "House",
                "state": "CA",
            }
        ],
    }
    path = tmp_path / "legislators_parties.json"
    write_legislators_parties_json(payload, path=path)
    rows = load_legislators_parties(path)
    assert match_party("Hon. Pete Aguilar", legislators=rows) == "Democrat"
    assert match_party("Pete Aguilar", legislators=rows) == "Democrat"


def test_match_party_last_state_chamber_fallback(tmp_path: Path):
    payload = {
        "meta": {"source": "test", "updated": "2026-01-01", "count": 1},
        "legislators": [
            {
                "official_full": "Alma Adams",
                "first": "Alma",
                "last": "Adams",
                "party": "Democrat",
                "chamber": "House",
                "state": "NC",
            }
        ],
    }
    path = tmp_path / "legislators_parties.json"
    write_legislators_parties_json(payload, path=path)
    rows = load_legislators_parties(path)
    # Middle name in disclosure — exact key misses; last+state+chamber hits.
    assert (
        match_party(
            "Hon. Alma Shealey Adams",
            chamber="House",
            state="NC",
            legislators=rows,
        )
        == "Democrat"
    )


def _legislator(first: str, last: str, party: str, chamber: str, state: str, full: str = "") -> dict[str, str]:
    return {
        "official_full": full or f"{first} {last}",
        "first": first,
        "last": last,
        "party": party,
        "chamber": chamber,
        "state": state,
    }


_ROSTER = [
    _legislator("Kelly", "Morrison", "Democrat", "House", "MN"),
    _legislator("August", "Pfluger", "Republican", "House", "TX"),
    _legislator("Neal", "Dunn", "Republican", "House", "FL", full="Neal P. Dunn"),
    _legislator("Nanette", "Barragán", "Democrat", "House", "CA", full="Nanette Diaz Barragán"),
    _legislator("Mike", "Garcia", "Republican", "House", "CA"),
    _legislator("Robert", "Garcia", "Democrat", "House", "CA"),
    _legislator("Jim", "Banks", "Republican", "Senate", "IN"),
    _legislator("Mitch", "McConnell", "Republican", "Senate", "KY"),
    _legislator("Mike", "Rogers", "Republican", "House", "AL"),
    _legislator("Mike", "Rogers", "Republican", "Senate", "MI"),
]


@pytest.mark.parametrize(
    ("name", "chamber", "state", "party"),
    [
        # Middle name, no state: filer's first + last token hits first+last.
        ("Hon. Kelly Louise Morrison", "House", "", "Democrat"),
        # Suffixes and credentials hide the real last name.
        ("Hon. August Lee Pfluger II", "House", "TX", "Republican"),
        ("Hon. Neal Patrick Dunn, MD, FACS", "House", "FL", "Republican"),
        # Accent in the roster, none in the disclosure.
        ("Hon. Nanette Barragan", "House", "CA", "Democrat"),
        # Two Garcias in CA: the first initial picks Mike over Robert.
        ("Hon. Michael Garcia", "House", "CA", "Republican"),
        # Title embedded mid-name, and the member has since moved to the Senate.
        ("Hon. James E Hon Banks", "House", "IN", "Republican"),
        # No state at all: last name + chamber + initial of a given name.
        ("A. Mitchell McConnell Jr.", "Senate", "", "Republican"),
        # Unknown filer stays blank.
        ("Unknown Candidate", "House", "ZZ", ""),
    ],
)
def test_match_party_messy_disclosure_names(name, chamber, state, party):
    assert match_party(name, chamber=chamber, state=state, legislators=_ROSTER) == party


def test_match_state_narrows_homonyms_only_when_unambiguous():
    assert match_state("Hon. Kelly Louise Morrison", chamber="House", legislators=_ROSTER) == "MN"
    # Two Mike Rogers (AL House, MI Senate): the chamber breaks the tie.
    assert match_state("Mike Rogers", chamber="Senate", legislators=_ROSTER) == "MI"
    # Without a chamber the name alone can't choose a state.
    assert match_state("Mike Rogers", legislators=_ROSTER) == ""


def test_match_party_rejects_same_name_in_another_state():
    assert match_party("Kelly Morrison", chamber="House", state="TX", legislators=_ROSTER) == ""


def test_backfill_member_parties(tmp_path: Path):
    db_path = tmp_path / "test.sqlite"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    upsert_member(conn, full_name="Hon. Pete Aguilar", chamber="House", state="CA")
    upsert_member(conn, full_name="Unknown Candidate", chamber="House", state="ZZ")

    path = tmp_path / "legislators_parties.json"
    write_legislators_parties_json(
        {
            "meta": {"source": "test", "updated": "2026-01-01", "count": 1},
            "legislators": [
                {
                    "official_full": "Pete Aguilar",
                    "first": "Pete",
                    "last": "Aguilar",
                    "party": "Democrat",
                    "chamber": "House",
                    "state": "CA",
                }
            ],
        },
        path=path,
    )
    stats = backfill_member_parties(conn, path=path)
    assert stats["updated"] == 1
    assert stats["unmatched"] == 1
    party = conn.execute(
        "SELECT party FROM members WHERE full_name = ?",
        ("Hon. Pete Aguilar",),
    ).fetchone()["party"]
    assert party == "Democrat"
    conn.close()


def test_build_payload_prefers_current():
    historical = [
        {
            "name": {"first": "Pete", "last": "Aguilar", "official_full": "Pete Aguilar"},
            "terms": [
                {
                    "type": "rep",
                    "start": "2015-01-06",
                    "end": "2017-01-03",
                    "state": "CA",
                    "party": "Democrat",
                }
            ],
        }
    ]
    current = [
        {
            "name": {"first": "Pete", "last": "Aguilar", "official_full": "Pete Aguilar"},
            "terms": [
                {
                    "type": "rep",
                    "start": "2025-01-03",
                    "end": "2027-01-03",
                    "state": "CA",
                    "party": "Democrat",
                }
            ],
        }
    ]
    payload = build_legislators_payload(current, historical)
    assert payload["meta"]["count"] == 1
    assert payload["legislators"][0]["party"] == "Democrat"


def test_bipartisan_with_enriched_parties():
    frame = pd.DataFrame(
        [
            {
                "member": "Alice",
                "party": "Democrat",
                "ticker": "AAPL",
                "transaction_type": "P",
                "transaction_date": pd.Timestamp("2024-06-01"),
                "asset_type": "Stock",
                "asset_name_raw": "Apple",
                "asset_name_normalized": "Apple",
                "issuer_name": "Apple",
            },
            {
                "member": "Bob",
                "party": "Republican",
                "ticker": "AAPL",
                "transaction_type": "P",
                "transaction_date": pd.Timestamp("2024-06-15"),
                "asset_type": "Stock",
                "asset_name_raw": "Apple",
                "asset_name_normalized": "Apple",
                "issuer_name": "Apple",
            },
        ]
    )
    out = bipartisan_tickers(frame, window_days=90)
    assert not out.empty
    assert (out["ticker"] == "AAPL").any()


def test_vendored_legislators_parties_json_loads():
    """Repo should ship data/legislators_parties.json for offline overlay."""
    from src.member_parties import LEGISLATORS_PARTIES_PATH

    if not LEGISLATORS_PARTIES_PATH.exists():
        pytest.skip("legislators_parties.json not vendored yet")
    rows = load_legislators_parties()
    assert len(rows) > 100
    assert any(r["party"] in {"Democrat", "Republican"} for r in rows)
