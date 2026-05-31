from __future__ import annotations

import pandas as pd

from src.dashboard_shared.tables import TableConfig, build_table_html, resolve_table_theme
from src.dashboard_shared.dashboard_tables import (
    asset_type_feed_label,
    build_summary_table_html,
    build_transaction_table_html,
    transaction_type_feed_label,
)


def test_transaction_type_feed_label():
    assert transaction_type_feed_label("P") == ("Purchase", "buy")
    assert transaction_type_feed_label("S (partial)") == ("Sale (Partial)", "sell-partial")
    assert transaction_type_feed_label("S") == ("Sale (Full)", "sell")


def test_asset_type_feed_label():
    assert asset_type_feed_label("equity") == "Stock"
    assert asset_type_feed_label("bond", "Corpus Christi Tex Utility") == "Bond"
    assert asset_type_feed_label("unknown", "Municipal Revenue Bond") == "Municipal Security"


def test_build_transaction_table_html_includes_columns():
    row = {
        "member": "David McCormick",
        "chamber": "Senate",
        "party": "R",
        "issuer_name": "Corpus Christi Tex Utility",
        "asset_type": "bond",
        "asset_name_raw": "Rate/Coupon: 5% Matures: 2030",
        "transaction_type": "P",
        "amount_range_raw": "$100,001 - $250,000",
        "amount_low": 100001,
        "amount_high": 250000,
        "filing_date": "2026-05-28",
        "transaction_date": "2026-04-30",
    }
    html = build_transaction_table_html(pd.DataFrame([row]))
    assert "Purchase" in html
    assert "David McCormick" in html
    assert "28/05/2026" in html
    assert "Politician" in html
    assert "dashboard-table" in html


def test_build_summary_table_html():
    frame = pd.DataFrame([{"ticker": "NVDA", "trades": 12, "first_trade": "2026-01-15"}])
    html = build_summary_table_html(
        frame,
        columns=["ticker", "trades", "first_trade"],
        headers={"ticker": "Ticker", "trades": "Trades", "first_trade": "First trade"},
    )
    assert "NVDA" in html
    assert "15/01/2026" in html
    assert "dt-light" in html
    # Leading whitespace before tags makes st.markdown render tables as code blocks.
    assert html.startswith("<div class=\"dashboard-table")


def test_build_transaction_table_html_compact():
    row = {
        "member": "Jane Doe",
        "chamber": "House",
        "party": "D",
        "ticker": "AAPL",
        "asset_type": "stock",
        "transaction_type": "P",
        "amount_low": 1000,
        "amount_high": 5000,
        "filing_date": "2026-05-01",
        "transaction_date": "2026-04-15",
    }
    html = build_transaction_table_html(pd.DataFrame([row]), show_return_legend=False)
    assert html.startswith("<div class=\"dashboard-table")
    assert "<table class=\"dt-table\">" in html
    assert "Jane Doe" in html


def test_resolve_table_theme_defaults_light():
    assert resolve_table_theme("light") == "dt-light"
    assert resolve_table_theme("dark") == "dt-dark"


def test_build_table_html_color_and_link_columns():
    frame = pd.DataFrame([{"member": "Alice", "relevant_trades": 5, "relevance_pct": 12.5}])
    html = build_table_html(
        frame,
        TableConfig(
            columns=["member", "relevant_trades", "relevance_pct"],
            headers={"member": "Member", "relevant_trades": "Relevant", "relevance_pct": "Relevance %"},
            link_columns={
                "member": {"page": "Members", "query": {"member": "member"}},
                "relevant_trades": {
                    "page": "Members",
                    "query": {"member": "member", "view": "committee_relevance"},
                },
            },
        ),
    )
    assert "dt-light" in html
    assert "dt-cell-accent" in html
    assert "dt-cell-pct" in html
    assert 'href="/members?member=Alice' in html
    assert "12.5" in html
