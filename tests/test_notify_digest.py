"""Weekly digest: the week's shape, and whether the pipeline is alive."""
from __future__ import annotations

import pandas as pd

from src.notify.digest import compute_digest_stats, render_digest
from src.notify.events import KIND_LARGE, KIND_OPTION, Event


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
        "amount_low": 15_001.0,
        "amount_high": 50_000.0,
        "amount_range_raw": "$15,001 - $50,000",
        "confidence_score": 1.0,
        "review_status": "resolved",
        "source_url": "",
        "raw_document_path": "",
        "doc_id": "doc1",
        "source_hash": "hash1",
        "disclosure_url": "",
    }
    base.update(over)
    return base


def test_empty_week_reports_zero_rows_not_a_crash():
    stats = compute_digest_stats(pd.DataFrame(), total_rows=1_000, stale_days=2)
    assert stats.rows == 0
    assert stats.total_rows == 1_000
    text = render_digest(stats)
    assert "No new disclosures" in text
    assert "1,000 transactions stored" in text


def test_stats_split_buys_and_sells_and_rank_members():
    frame = pd.DataFrame(
        [
            _row(member="Alice Example", transaction_type="P", amount_low=100_000.0,
                 amount_high=250_000.0, source_hash="a"),
            _row(member="Alice Example", transaction_type="S", amount_low=1_001.0,
                 amount_high=15_000.0, source_hash="b"),
            _row(member="Bob Example", transaction_type="P", amount_low=15_001.0,
                 amount_high=50_000.0, ticker="AAPL", source_hash="c"),
        ]
    )
    stats = compute_digest_stats(frame, total_rows=3, stale_days=0)
    assert stats.rows == 3
    assert stats.members == 2
    assert stats.tickers == 2
    assert stats.buys == 2
    assert stats.sells == 1
    assert stats.buy_low == 115_001.0
    assert stats.sell_low == 1_001.0
    # Ranked by disclosed value, so Alice leads.
    assert stats.top_members[0][0] == "Alice Example"
    assert stats.top_members[0][1] == 2


def test_ticker_ranking_prefers_breadth_of_members():
    frame = pd.DataFrame(
        [
            _row(member="Alice Example", ticker="ONE", source_hash="a"),
            _row(member="Alice Example", ticker="ONE", source_hash="b"),
            _row(member="Alice Example", ticker="ONE", source_hash="c"),
            _row(member="Bob Example", ticker="MANY", source_hash="d"),
            _row(member="Carol Example", ticker="MANY", source_hash="e"),
        ]
    )
    stats = compute_digest_stats(frame, total_rows=5, stale_days=0)
    assert stats.top_tickers[0][0] == "MANY", "2 members beats 3 trades by one member"
    assert stats.top_tickers[0][2] == 2


def test_alert_counts_come_from_the_events_list():
    events = [
        Event(kind=KIND_LARGE, title="a"),
        Event(kind=KIND_LARGE, title="b"),
        Event(kind=KIND_OPTION, title="c"),
    ]
    stats = compute_digest_stats(
        pd.DataFrame([_row()]), events=events, total_rows=1, stale_days=1
    )
    assert stats.large_events == 2
    assert stats.option_events == 1
    assert stats.late_events == 0
    assert "2 large · 1 options" in render_digest(stats)


def test_stale_pipeline_is_called_out():
    stats = compute_digest_stats(pd.DataFrame(), total_rows=10, stale_days=68)
    text = render_digest(stats, stale_threshold_days=10)
    assert "No new row for 68 days" in text
    assert "ingest.log" in text


def test_fresh_pipeline_reports_quietly():
    stats = compute_digest_stats(pd.DataFrame(), total_rows=10, stale_days=1)
    text = render_digest(stats, stale_threshold_days=10)
    assert "Last new row 1 day ago" in text
    assert "may be failing" not in text


def test_missing_ingest_timestamp_is_reported_rather_than_assumed_fresh():
    stats = compute_digest_stats(pd.DataFrame(), total_rows=0, stale_days=None)
    assert "has the pipeline ever run" in render_digest(stats)


def test_singular_plural_reads_correctly():
    frame = pd.DataFrame([_row()])
    stats = compute_digest_stats(frame, total_rows=1, stale_days=1)
    text = render_digest(stats)
    assert "1 new row · 1 member · 1 ticker" in text
    assert "1 trade," in text
    assert "1 trades" not in text
