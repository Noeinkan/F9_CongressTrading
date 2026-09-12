"""Detection policy: what earns a message and what stays quiet."""
from __future__ import annotations

import pandas as pd

from src.notify.events import (
    KIND_CLUSTER,
    KIND_LARGE,
    KIND_LATE,
    KIND_OPTION,
    collect_events,
    detect_clusters,
    member_label,
    prepare_frame,
)

LARGE = 50_000.0
OPTION = 15_000.0
LATE_DAYS = 45


def _row(**over) -> dict:
    base = {
        "member": "Alice Example",
        "chamber": "House",
        "party": "D",
        "state": "CA",
        "filing_type": "PTR",
        "filing_date": pd.Timestamp("2026-03-01"),
        "transaction_date": pd.Timestamp("2026-02-20"),
        "owner_type": "self",
        "asset_name_raw": "Example Corp Common Stock",
        "asset_name_normalized": "example corp",
        "asset_type": "stock",
        "issuer_name": "Example Corp",
        "ticker": "EXC",
        "sector": "Technology",
        "industry": "Software",
        "transaction_type": "P",
        "transaction_type_label": "Buy",
        "amount_low": 1_001.0,
        "amount_high": 15_000.0,
        "amount_range_raw": "$1,001 - $15,000",
        "confidence_score": 1.0,
        "review_status": "resolved",
        "source_url": "https://example.test/doc.pdf",
        "raw_document_path": "",
        "doc_id": "doc1",
        "source_hash": "hash1",
        "disclosure_url": "https://example.test/doc.pdf",
    }
    base.update(over)
    return base


def _frame(*rows: dict) -> pd.DataFrame:
    return pd.DataFrame(list(rows))


def _collect(frame: pd.DataFrame, **over):
    kwargs = {
        "context_frame": None,
        "large_trade_usd": LARGE,
        "option_trade_usd": OPTION,
        "late_filing_days": LATE_DAYS,
        "cluster_min_members": 3,
        "cluster_window_days": 45,
    }
    kwargs.update(over)
    return collect_events(frame, **kwargs)


# --------------------------------------------------------------------------- #
# Large trades
# --------------------------------------------------------------------------- #
def test_large_trade_keys_on_the_disclosed_floor():
    """A $50,001-$100,000 bucket clears the bar; $15,001-$50,000 does not."""
    events = _collect(
        _frame(
            _row(amount_low=50_001.0, amount_high=100_000.0, source_hash="big"),
            _row(amount_low=15_001.0, amount_high=50_000.0, source_hash="small"),
        )
    )
    assert [e.kind for e in events] == [KIND_LARGE]
    assert "EXC" in events[0].title


def test_nothing_notable_produces_no_events():
    assert _collect(_frame(_row(), _row(source_hash="h2"))) == []


# --------------------------------------------------------------------------- #
# Options
# --------------------------------------------------------------------------- #
def test_option_trade_is_reported_once_not_also_as_a_large_trade():
    """The more specific detector claims the row, so there is no duplicate."""
    events = _collect(
        _frame(
            _row(
                amount_low=100_000.0,
                amount_high=250_000.0,
                asset_name_raw="Example Corp Call Option $120 strike",
                asset_type="option",
            )
        )
    )
    assert len(events) == 1
    assert events[0].kind == KIND_OPTION
    assert "call" in events[0].title.lower()


def test_option_below_its_own_threshold_is_ignored():
    events = _collect(
        _frame(
            _row(
                amount_low=1_001.0,
                amount_high=15_000.0,
                asset_name_raw="Example Corp Put Option",
                asset_type="option",
            )
        )
    )
    assert events == []


# --------------------------------------------------------------------------- #
# Late filings
# --------------------------------------------------------------------------- #
def test_lateness_rides_along_as_a_tag_when_the_trade_is_already_reported():
    events = _collect(
        _frame(
            _row(
                amount_low=50_001.0,
                amount_high=100_000.0,
                transaction_date=pd.Timestamp("2026-01-01"),
                filing_date=pd.Timestamp("2026-04-01"),
            )
        )
    )
    assert len(events) == 1, "a big trade filed late is one message, not two"
    assert events[0].kind == KIND_LARGE
    assert "late" in events[0].lines[0]


def test_small_late_filing_is_reported_on_its_own():
    events = _collect(
        _frame(
            _row(
                transaction_date=pd.Timestamp("2026-01-01"),
                filing_date=pd.Timestamp("2026-04-01"),
            )
        )
    )
    assert [e.kind for e in events] == [KIND_LATE]
    assert "90 days late" in events[0].title


def test_filing_inside_the_deadline_is_not_late():
    events = _collect(
        _frame(
            _row(
                transaction_date=pd.Timestamp("2026-02-01"),
                filing_date=pd.Timestamp("2026-03-01"),
            )
        )
    )
    assert events == []


# --------------------------------------------------------------------------- #
# Tags
# --------------------------------------------------------------------------- #
def test_first_position_tag_is_added_by_the_tagger():
    events = _collect(
        _frame(_row(amount_low=50_001.0, amount_high=100_000.0)),
        tagger=lambda row: ["first position in EXC"],
    )
    assert "first position in EXC" in events[0].lines[0]


# --------------------------------------------------------------------------- #
# Clusters
# --------------------------------------------------------------------------- #
def _cluster_context() -> pd.DataFrame:
    return _frame(
        _row(member="Alice Example", ticker="NVDA", source_hash="a"),
        _row(member="Bob Example", ticker="NVDA", source_hash="b"),
        _row(member="Carol Example", ticker="NVDA", source_hash="c"),
    )


def test_cluster_reported_only_when_a_new_row_touches_that_ticker():
    context = _cluster_context()
    assert detect_clusters(
        context, new_tickers=["AAPL"], min_members=3, window_days=45
    ) == []
    found = detect_clusters(
        context, new_tickers=["NVDA"], min_members=3, window_days=45
    )
    assert [e.kind for e in found] == [KIND_CLUSTER]
    assert "NVDA" in found[0].title
    assert found[0].sort_value == 3.0


def test_cluster_suppressed_when_it_has_not_grown():
    found = detect_clusters(
        _cluster_context(),
        new_tickers=["NVDA"],
        min_members=3,
        window_days=45,
        is_new=lambda key, members: False,
    )
    assert found == []


def test_cluster_needs_the_minimum_member_count():
    context = _frame(
        _row(member="Alice Example", ticker="NVDA", source_hash="a"),
        _row(member="Bob Example", ticker="NVDA", source_hash="b"),
    )
    assert detect_clusters(
        context, new_tickers=["NVDA"], min_members=3, window_days=45
    ) == []


# --------------------------------------------------------------------------- #
# Labels
# --------------------------------------------------------------------------- #
def test_member_label_carries_chamber_party_and_state():
    row = prepare_frame(_frame(_row())).iloc[0]
    assert member_label(row) == "Rep. Alice Example (D-CA)"


def test_member_label_drops_the_title_already_in_the_name():
    """House filings store "Hon. X", which would render "Rep. Hon. X"."""
    row = prepare_frame(_frame(_row(member="Hon. Tim Moore", party="R", state=""))).iloc[0]
    assert member_label(row) == "Rep. Tim Moore (R)"


def test_member_label_survives_missing_party_and_state():
    row = prepare_frame(_frame(_row(party="", state="", chamber="Senate"))).iloc[0]
    assert member_label(row) == "Sen. Alice Example"


def test_empty_frame_is_handled():
    assert _collect(pd.DataFrame()) == []
