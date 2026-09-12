"""Message rendering: grouping by filing, dashboard links, compact amounts."""
from __future__ import annotations

import pandas as pd

from src.notify.digest import compute_digest_stats, render_digest
from src.notify.events import KIND_CLUSTER, KIND_LARGE, KIND_LATE, Event
from src.notify.format import render_event_message
from src.notify.links import DashboardLinks, anchor
from src.notify.money import compact_usd, disclosed_range

LINKS = DashboardLinks("https://dash.example/")


def _trade(**over) -> Event:
    base = dict(
        kind=KIND_LARGE,
        title="Sell · SMA — Rep. Kevin Hern (R-OK)",
        url="https://example.test/20034262.pdf",
        sort_value=500_001.0,
        member="Hon. Kevin Hern",
        member_label="Rep. Kevin Hern (R-OK)",
        ticker="SMA",
        action="Sell",
        asset="SMA",
        amount="$500K–$1M",
        low=500_001.0,
        high=1_000_000.0,
        traded_on=pd.Timestamp("2026-03-18"),
        filed="03 Apr 2026",
        group_key="Hon. Kevin Hern|20034262",
        direction="sell",
    )
    base.update(over)
    return Event(**base)


# --------------------------------------------------------------------------- #
# Money
# --------------------------------------------------------------------------- #
def test_compact_usd_drops_the_trailing_zero():
    assert compact_usd(15_001) == "$15K"
    assert compact_usd(250_000) == "$250K"
    assert compact_usd(2_500_000) == "$2.5M"
    assert compact_usd(800) == "$800"
    assert compact_usd(None) == ""
    assert compact_usd(float("nan")) == ""


def test_disclosed_range_marks_a_floor_without_a_ceiling():
    assert disclosed_range(100_001, 250_000) == "$100K–$250K"
    assert disclosed_range(500_001, 500_001) == "$500K+"
    assert disclosed_range(500_001, None) == "$500K+"
    assert disclosed_range(None, None) == ""


# --------------------------------------------------------------------------- #
# Links
# --------------------------------------------------------------------------- #
def test_links_mirror_the_frontend_routes():
    assert LINKS.home() == "https://dash.example/"
    assert LINKS.member("Hon. Kevin Hern") == "https://dash.example/members?member=Hon.%20Kevin%20Hern"
    assert LINKS.ticker("brk.b") == "https://dash.example/tickers?ticker=BRK.B"


def test_no_base_url_means_plain_text_not_broken_links():
    links = DashboardLinks("")
    assert links.member("Anyone") == ""
    assert anchor(links.member("Anyone"), "AT&T") == "AT&amp;T"


def test_anchor_escapes_the_label_and_the_url():
    html = anchor("https://x.test/?a=1&b=2", "<Rep>")
    assert html == '<a href="https://x.test/?a=1&amp;b=2">&lt;Rep&gt;</a>'


# --------------------------------------------------------------------------- #
# Event message
# --------------------------------------------------------------------------- #
def test_rows_from_one_filing_share_one_member_heading():
    events = [
        _trade(),
        _trade(ticker="TXN", asset="TXN", title="Sell · TXN — Rep. Kevin Hern (R-OK)"),
    ]
    text = render_event_message(events, new_row_count=2, links=LINKS)
    assert text.count("Rep. Kevin Hern (R-OK)") == 1
    assert text.count(">PDF</a>") == 1
    assert "🔴 Sell" in text
    assert 'href="https://dash.example/tickers?ticker=TXN"' in text
    assert 'href="https://dash.example/members?member=Hon.%20Kevin%20Hern"' in text


def test_separate_filings_render_separately():
    events = [_trade(), _trade(group_key="Hon. Kevin Hern|other", url="https://example.test/2.pdf")]
    text = render_event_message(events, new_row_count=2, links=LINKS)
    assert text.count(">PDF</a>") == 2


def test_senate_filing_without_pdf_still_links_the_member():
    senate = _trade(
        url="",
        member="Tommy Tuberville",
        member_label="Sen. Tommy Tuberville (R-AL)",
        group_key="Tommy Tuberville|ptr-1",
    )
    text = render_event_message([senate], new_row_count=1, links=LINKS)
    assert ">PDF</a>" not in text
    assert 'href="https://dash.example/members?member=Tommy%20Tuberville"' in text


def test_message_without_dashboard_url_still_renders_names():
    text = render_event_message([_trade()], new_row_count=1)
    assert "Rep. Kevin Hern (R-OK)" in text
    assert "dash.example" not in text
    assert "dashboard</a>" not in text


def test_long_filing_is_trimmed_with_a_count():
    events = [
        _trade(ticker=f"T{i}", asset=f"T{i}", sort_value=float(1_000_000 - i), dedupe_key=str(i))
        for i in range(7)
    ]
    text = render_event_message(events, new_row_count=7, links=LINKS)
    assert "… 3 more lines on this filing" in text


def test_repeats_of_one_trade_on_one_filing_fold_into_a_total():
    events = [
        _trade(ticker="ANDG", asset="ANDG", action="Sell (partial)", late_days=392,
               traded_on=pd.Timestamp("2025-01-20"), details=("Industrials", "first buy on record")),
        _trade(ticker="ANDG", asset="ANDG", action="Sell (partial)", late_days=27,
               low=250_001.0, high=500_000.0, sort_value=250_001.0,
               traded_on=pd.Timestamp("2026-01-20"), details=("Industrials",)),
    ]
    text = render_event_message(events, new_row_count=2, links=LINKS)
    line = next(line for line in text.splitlines() if "×2" in line)
    assert "$750K–$1.5M" in line
    assert "traded 20 Jan 2025–20 Jan 2026" in line
    assert "filed 27–392 days late" in line
    assert "Industrials" in line
    assert "first buy on record" not in line, "a tag true of one row is not true of the line"


def test_folded_line_says_how_many_rows_were_late():
    events = [
        _trade(ticker="ANDG", asset="ANDG", late_days=392),
        _trade(ticker="ANDG", asset="ANDG", late_days=None),
    ]
    text = render_event_message(events, new_row_count=2)
    assert "1 of 2 filed 392 days late" in text


def test_folded_total_is_a_floor_when_any_row_lacks_a_ceiling():
    events = [
        _trade(ticker="CNC", asset="CNC", low=100_001.0, high=100_001.0),
        _trade(ticker="CNC", asset="CNC", low=100_001.0, high=250_000.0),
    ]
    text = render_event_message(events, new_row_count=2)
    assert "×2 · $200K+" in text


def test_overflow_points_to_the_full_list():
    events = [
        _trade(kind=KIND_LATE, group_key=f"m{i}|d{i}", sort_value=float(i), direction="")
        for i in range(10)
    ]
    text = render_event_message(events, new_row_count=10, links=LINKS)
    assert "… and 7 more" in text
    assert 'href="https://dash.example/raw">Full list</a>' in text


def test_cluster_links_the_ticker_and_each_member():
    cluster = Event(
        kind=KIND_CLUSTER,
        title="Coordinated buy · NVDA — 3 members",
        sort_value=3.0,
        ticker="NVDA",
        action="Coordinated buy",
        asset="NVDA",
        details=("5 trades between 01 Mar 2026 and 20 Mar 2026",),
        direction="buy",
        members=("Hon. Alice Example", "Bob Example", "Carol Example"),
    )
    text = render_event_message([cluster], new_row_count=1, links=LINKS)
    assert 'tickers?ticker=NVDA">NVDA</a>' in text
    assert 'members?member=Hon.%20Alice%20Example">Alice Example</a>' in text
    assert "3 members" in text


def test_event_without_structure_falls_back_to_title_and_lines():
    text = render_event_message(
        [Event(kind=KIND_LARGE, title="Something & more", lines=("detail",))],
        new_row_count=1,
    )
    assert "Something &amp; more" in text
    assert "detail" in text


# --------------------------------------------------------------------------- #
# Digest
# --------------------------------------------------------------------------- #
def test_digest_uses_member_labels_and_links():
    frame = pd.DataFrame(
        [
            {
                "member": "Hon. Alice Example",
                "chamber": "House",
                "party": "D",
                "state": "CA",
                "ticker": "EXC",
                "transaction_type": "P",
                "transaction_date": pd.Timestamp("2026-02-20"),
                "filing_date": pd.Timestamp("2026-03-01"),
                "asset_type": "stock",
                "asset_name_raw": "Example Corp Common Stock",
                "asset_name_normalized": "example corp",
                "issuer_name": "Example Corp",
                "amount_low": 15_001.0,
                "amount_high": 50_000.0,
            }
        ]
    )
    stats = compute_digest_stats(frame, total_rows=1, stale_days=1)
    text = render_digest(stats, links=LINKS)
    assert "Rep. Alice Example (D-CA)</a>" in text
    assert "Hon. Alice" not in text, "display text drops the House title"
    assert 'tickers?ticker=EXC">EXC</a>' in text
    assert "$15K–$50K" in text
    assert "Open the dashboard" in text
