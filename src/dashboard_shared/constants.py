from __future__ import annotations

from datetime import date

from ..config import DATA_DIR

NORMALIZED_EXPORT_PATH = DATA_DIR / "congress_trades.csv"
REVIEW_EXPORT_PATH = DATA_DIR / "review_queue.csv"

# Default transaction date range in the sidebar (clamped to available data).
DEFAULT_TRANSACTION_FILTER_START = date(2023, 1, 1)

THEME = {
    "bg": "#f4efe6",
    "bg_panel": "rgba(255, 250, 241, 0.92)",
    "bg_panel_strong": "#fffaf1",
    "ink": "#1d232c",
    "ink_soft": "#404854",
    "muted": "#5f6773",
    "line": "rgba(48, 58, 71, 0.14)",
    "accent": "#a64b2a",
    "accent_deep": "#7e351d",
    "accent_soft": "rgba(166, 75, 42, 0.10)",
    "navy": "#20344a",
    "teal": "#2d6f6d",
    "gold": "#c6922b",
    "hero_ink": "#f7f0e6",
    "hero_ink_soft": "rgba(247, 240, 230, 0.76)",
    "sidebar_bg": "linear-gradient(180deg, #171b22 0%, #1f2530 52%, #252b36 100%)",
    "sidebar_ink": "#fbf6ee",
    "sidebar_muted": "rgba(241, 232, 220, 0.76)",
    "sidebar_border": "rgba(255, 255, 255, 0.12)",
    "sidebar_field": "rgba(9, 13, 19, 0.88)",
    "sidebar_field_focus": "#101a24",
    "sidebar_card": "linear-gradient(180deg, rgba(255, 255, 255, 0.08) 0%, rgba(255, 255, 255, 0.04) 100%)",
    "button_ink": "#fff6eb",
    "shadow": "0 18px 40px rgba(45, 35, 24, 0.09)",
    "chart_grid": "rgba(95, 103, 115, 0.16)",
    # Contrast-first tokens (main column text + chart axes/legends vs warm background)
    "ui_caption": "#15202e",
    "ui_body_secondary": "#2a3442",
    "chart_axis_label": "#111820",
    "chart_axis_title": "#06090d",
    "chart_legend_label": "#0f141c",
    "chart_legend_title": "#05070a",
    "chart_view_fill": "rgba(255, 253, 248, 0.98)",
    "chart_view_stroke": "rgba(18, 24, 34, 0.18)",
    "chart_grid_major": "rgba(18, 24, 34, 0.24)",
    "plotly_paper": "#fff8f0",
    "plotly_scene_bg": "#fffaf3",
    "plotly_axis_ink": "#0c1018",
    "plotly_tick_ink": "#141b26",
    "plotly_legend_ink": "#0c1018",
}

DASHBOARD_COPY = {
    "page_title": "Congress Trading Dashboard",
    "eyebrow": "Congress Trading",
    "hero_title": "Track congressional trades without digging through raw filings.",
    "hero_copy": (
        "Filter normalized House and Senate disclosures, inspect concentration by member and ticker, "
        "and surface the review backlog before it turns into analysis debt."
    ),
    "empty_hero_title": "Normalized activity dashboard",
    "empty_hero_copy": (
        "Analyst workspace for House and Senate disclosures. Load the ingestion pipeline first, then use this page "
        "to inspect trades, concentration, and unresolved records."
    ),
    "sidebar_header": "Filters",
    "sidebar_dataset_expander": "Full dataset (reference)",
    "sidebar_dataset_expander_caption": "Totals across every loaded row; filters below apply on top of this.",
    "sidebar_slice_summary_title": "Active slice",
    "current_slice": "Current slice",
    "no_chamber_selected": "No chamber selected",
    "no_dated_trades": "No dated trades",
    "empty_state": "No normalized transactions found yet. Run ingestion or export first, then refresh the dashboard.",
    "overview_kicker": "Overview",
    "overview_title": "Where activity is clustering",
    "overview_copy": "Use these charts to identify bursts of disclosure activity, concentration by member, and which transaction types dominate the current slice.",
    "review_kicker": "Review Queue",
    "review_title": "Triage unresolved records",
    "review_copy": "These rows still require manual confirmation or a better asset resolution. Treat this tab as the backlog that determines analysis quality.",
    "raw_kicker": "Raw Data",
    "raw_title": "Inspect and export the working dataset",
    "raw_copy": "This table is the normalized slice after all active filters. Use it to audit rows before exporting or doing separate downstream analysis.",
    "tab_overview": "Overview",
    "tab_review": "Review Queue",
    "tab_raw": "Raw Data",
    "overview_detail_heading": "Latest activity and ticker drill-down",
    "overview_detail_caption": "Row-level data and per-ticker views; use the summary charts above for the big picture.",
    "sub_monthly_activity": "Monthly activity",
    "sub_top_members": "Top members",
    "sub_chamber_mix": "Chamber mix",
    "sub_transaction_type_mix": "Transaction type mix",
    "sub_top_tickers": "Top tickers",
    "sub_latest_transactions": "Latest transactions",
    "sub_ticker_who_when": "Ticker activity: who traded and when",
    "sub_cumulative_exposure": "Cumulative exposure (median of amount range)",
    "cumulative_exposure_caption": (
        "Per member and selected ticker: running sum of signed dollar amounts. **Buy (P)** adds the **median** of each "
        "disclosure amount range (between low and high when both exist); **Sell** and **partial sell** subtract. "
        "Same-day trades are ordered by filing date. This is a rough notional proxy, not share count."
    ),
    "ticker_chart_caption": (
        "Each row is one member of Congress; the horizontal axis is when the trade occurred. "
        "Vertical dashed lines mark month starts (or weeks if the window is short). "
        "Each dot is one disclosure — color is transaction type. Pick a ticker or use the override."
    ),
    "ticker_color_key_title": "Dot colors",
    "sub_ticker_3d": "Same ticker in 3D (rotate / zoom with mouse)",
    "ticker_3d_caption": (
        "**X** = transaction date · **Y** = member · **Z** = log₁₀(estimated range midpoint + 1) so trade size has depth. "
        "Legend at top matches dot colors (Buy / Sell / …). Drag the plot to rotate."
    ),
    "chart_caption_monthly": (
        "**What you see:** one series — how many disclosure **rows** fall in each **calendar month** after your filters. "
        "The fill color is decorative (not buy vs sell)."
    ),
    "chart_caption_rank_members": (
        "**What you see:** horizontal bars = **transaction count** per member in the current slice. "
        "Single bar color (navy) — length is the signal, not hue."
    ),
    "chart_caption_rank_tickers": (
        "**What you see:** horizontal bars = **transaction count** per resolved **ticker** in the current slice. "
        "Single bar color (gold) — length is the signal."
    ),
    "chart_caption_mix_chamber": (
        "**What you see:** vertical bars = **row counts** by **chamber** (House vs Senate, etc.) in the filtered data."
    ),
    "chart_caption_mix_txn_type": (
        "**What you see:** vertical bars = **row counts** by **transaction type label** (Buy / Sell / … from disclosure codes)."
    ),
    "chart_caption_mix_review_reason": "**What you see:** how many review-queue rows per **reason** code.",
    "chart_caption_mix_review_status": "**What you see:** how many review-queue rows per **status** (open, …).",
    "chart_caption_cumulative": (
        "**Legend:** colored lines = **member** (up to 16 with the most trades on this ticker). "
        "Hover a point for type and signed dollar delta. Y-axis = cumulative signed median $."
    ),
    "sidebar_pick_member_label": "Member",
    "sidebar_pick_ticker_label": "Ticker",
    "sidebar_pick_issuer_label": "Issuer",
    "sidebar_member_filter_hint": "Open the menu and type to narrow; pick a name or type a substring (Streamlit combobox). Clear with ✕ for everyone.",
    "sidebar_member_filter_placeholder": "Everyone — type or pick",
    "sidebar_ticker_filter_hint": "Type to narrow symbols; pick one or type a substring. “No ticker” or “-” filters unresolved tickers.",
    "sidebar_ticker_filter_placeholder": "Any ticker — type or pick",
    "sidebar_issuer_filter_hint": "Type to narrow issuers; pick or type a substring. “Blank issuer” or “-” for empty names.",
    "sidebar_issuer_filter_placeholder": "Any issuer — type or pick",
    "sub_records_needing_review": "Records needing review",
    "sub_filtered_dataset": "Filtered normalized dataset",
}

TRANSACTION_COLUMNS = [
    "member",
    "chamber",
    "party",
    "state",
    "filing_type",
    "filing_date",
    "transaction_date",
    "owner_type",
    "asset_name_raw",
    "asset_name_normalized",
    "asset_type",
    "issuer_name",
    "ticker",
    "transaction_type",
    "amount_low",
    "amount_high",
    "amount_range_raw",
    "confidence_score",
    "review_status",
    "source_url",
    "raw_document_path",
    "doc_id",
]

REVIEW_COLUMNS = [
    "reason",
    "status",
    "notes",
    "member",
    "chamber",
    "filing_type",
    "filing_date",
    "transaction_date",
    "asset_name_raw",
    "asset_name_normalized",
    "asset_type",
    "ticker",
    "transaction_type_label",
    "transaction_type",
    "amount_range_raw",
    "confidence_score",
    "review_status",
    "raw_document_path",
    "source_page",
    "source_row",
]

# Sidebar typeahead: option labels for blank ticker / issuer (must match filter logic below).
_SIDEBAR_NO_TICKER = "— No ticker —"
_SIDEBAR_NO_ISSUER = "— Blank issuer —"

SQLITE_TRANSACTION_QUERY = """
SELECT
    m.full_name AS member,
    f.chamber AS chamber,
    m.party AS party,
    m.state AS state,
    f.filing_type AS filing_type,
    f.filing_date AS filing_date,
    t.transaction_date AS transaction_date,
    t.owner_type AS owner_type,
    t.asset_name_raw AS asset_name_raw,
    t.asset_name_normalized AS asset_name_normalized,
    t.asset_type AS asset_type,
    COALESCE(i.issuer_name, '') AS issuer_name,
    t.ticker AS ticker,
    t.transaction_type AS transaction_type,
    t.amount_low AS amount_low,
    t.amount_high AS amount_high,
    t.amount_range_raw AS amount_range_raw,
    t.confidence_score AS confidence_score,
    t.review_status AS review_status,
    f.source_url AS source_url,
    f.raw_document_path AS raw_document_path,
    f.doc_id AS doc_id
FROM transactions t
JOIN filings f ON f.id = t.filing_id
JOIN members m ON m.id = f.member_id
LEFT JOIN issuers i ON i.id = t.issuer_id
ORDER BY t.transaction_date DESC, f.filing_date DESC, m.full_name ASC
"""

SQLITE_REVIEW_QUERY = """
SELECT
    rq.reason AS reason,
    rq.status AS status,
    rq.notes AS notes,
    m.full_name AS member,
    f.chamber AS chamber,
    f.filing_type AS filing_type,
    f.filing_date AS filing_date,
    t.transaction_date AS transaction_date,
    t.asset_name_raw AS asset_name_raw,
    t.asset_name_normalized AS asset_name_normalized,
    t.asset_type AS asset_type,
    t.ticker AS ticker,
    t.transaction_type AS transaction_type,
    t.amount_range_raw AS amount_range_raw,
    t.confidence_score AS confidence_score,
    t.review_status AS review_status,
    f.raw_document_path AS raw_document_path,
    t.source_page AS source_page,
    t.source_row AS source_row
FROM review_queue rq
JOIN transactions t ON t.id = rq.transaction_id
JOIN filings f ON f.id = t.filing_id
JOIN members m ON m.id = f.member_id
ORDER BY rq.updated_at DESC, f.filing_date DESC
"""
