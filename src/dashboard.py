from __future__ import annotations

from datetime import date
from io import BytesIO
from pathlib import Path
import sqlite3

import altair as alt
import pandas as pd
import streamlit as st

from .config import DATA_DIR, DB_PATH
from .db import get_connection, init_db

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
    "chart_grid": "rgba(95, 103, 115, 0.12)",
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
    "sub_monthly_activity": "Monthly activity",
    "sub_top_members": "Top members",
    "sub_chamber_mix": "Chamber mix",
    "sub_transaction_type_mix": "Transaction type mix",
    "sub_top_tickers": "Top tickers",
    "sub_latest_transactions": "Latest transactions",
    "sub_ticker_who_when": "Ticker activity: who traded and when",
    "ticker_chart_caption": "Choose a resolved ticker below, or type one in the override field. Points are individual disclosures in your current filter slice.",
    "sidebar_pick_member_label": "Member",
    "sidebar_pick_ticker_label": "Ticker",
    "sidebar_pick_issuer_label": "Issuer",
    "sub_records_needing_review": "Records needing review",
    "sub_filtered_dataset": "Filtered normalized dataset",
}

TRANSACTION_COLUMNS = [
    "member",
    "chamber",
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
    "transaction_type",
    "amount_range_raw",
    "confidence_score",
    "review_status",
    "raw_document_path",
    "source_page",
    "source_row",
]

# Sidebar selectbox sentinels (stable labels; shown first in each dropdown).
_SIDEBAR_ANY = "— Any —"
_SIDEBAR_NO_TICKER = "— No ticker —"
_SIDEBAR_NO_ISSUER = "— No issuer —"

SQLITE_TRANSACTION_QUERY = """
SELECT
    m.full_name AS member,
    f.chamber AS chamber,
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
    f.raw_document_path AS raw_document_path
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


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _empty_frame(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=columns)


def _read_sqlite(query: str) -> pd.DataFrame:
    conn = get_connection()
    try:
        init_db(conn)
        return pd.read_sql_query(query, conn)
    finally:
        conn.close()


def _prepare_transactions(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.copy()
    for column in TRANSACTION_COLUMNS:
        if column not in data.columns:
            data[column] = pd.NA

    data["filing_date"] = pd.to_datetime(data["filing_date"], errors="coerce")
    data["transaction_date"] = pd.to_datetime(data["transaction_date"], errors="coerce")
    data["confidence_score"] = pd.to_numeric(data["confidence_score"], errors="coerce").fillna(0.0)
    data["amount_low"] = pd.to_numeric(data["amount_low"], errors="coerce")
    data["amount_high"] = pd.to_numeric(data["amount_high"], errors="coerce")
    data["estimated_value"] = data[["amount_low", "amount_high"]].mean(axis=1, skipna=True)
    data["ticker"] = data["ticker"].fillna("").astype(str).str.upper()
    data["member"] = data["member"].fillna("Unknown")
    data["issuer_name"] = data["issuer_name"].fillna("")
    data["asset_name_normalized"] = data["asset_name_normalized"].fillna("")
    data["asset_name_raw"] = data["asset_name_raw"].fillna("")
    data["owner_type"] = data["owner_type"].fillna("unspecified")
    data["review_status"] = data["review_status"].fillna("pending")
    data["asset_type"] = data["asset_type"].fillna("unknown")
    data["transaction_type"] = data["transaction_type"].fillna("unknown")
    data["month"] = data["transaction_date"].dt.to_period("M").dt.to_timestamp()
    return data[TRANSACTION_COLUMNS + ["estimated_value", "month"]]


def _prepare_review(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.copy()
    for column in REVIEW_COLUMNS:
        if column not in data.columns:
            data[column] = pd.NA

    data["filing_date"] = pd.to_datetime(data["filing_date"], errors="coerce")
    data["transaction_date"] = pd.to_datetime(data["transaction_date"], errors="coerce")
    data["confidence_score"] = pd.to_numeric(data["confidence_score"], errors="coerce").fillna(0.0)
    data["status"] = data["status"].fillna("open")
    data["reason"] = data["reason"].fillna("review")
    data["notes"] = data["notes"].fillna("")
    return data[REVIEW_COLUMNS]


def load_transactions() -> tuple[pd.DataFrame, str]:
    conn = get_connection()
    try:
        init_db(conn)
        if _table_exists(conn, "transactions"):
            count = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
            if count:
                return _prepare_transactions(pd.read_sql_query(SQLITE_TRANSACTION_QUERY, conn)), f"sqlite:{DB_PATH.name}"
    finally:
        conn.close()

    if NORMALIZED_EXPORT_PATH.exists():
        return _prepare_transactions(pd.read_csv(NORMALIZED_EXPORT_PATH)), f"csv:{NORMALIZED_EXPORT_PATH.name}"

    return _prepare_transactions(_empty_frame(TRANSACTION_COLUMNS)), "empty"


def load_review_queue(transactions: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    conn = get_connection()
    try:
        init_db(conn)
        if _table_exists(conn, "review_queue"):
            count = conn.execute("SELECT COUNT(*) FROM review_queue").fetchone()[0]
            if count:
                return _prepare_review(pd.read_sql_query(SQLITE_REVIEW_QUERY, conn)), f"sqlite:{DB_PATH.name}"
    finally:
        conn.close()

    if REVIEW_EXPORT_PATH.exists():
        return _prepare_review(pd.read_csv(REVIEW_EXPORT_PATH)), f"csv:{REVIEW_EXPORT_PATH.name}"

    unresolved = transactions.loc[transactions["review_status"] != "resolved"].copy()
    if unresolved.empty:
        return _prepare_review(_empty_frame(REVIEW_COLUMNS)), "derived:none"

    unresolved["reason"] = "review_status"
    unresolved["status"] = unresolved["review_status"].fillna("open")
    unresolved["notes"] = "Derived from unresolved normalized transactions"
    unresolved["source_page"] = pd.NA
    unresolved["source_row"] = pd.NA
    unresolved["filing_type"] = unresolved["filing_type"].fillna("PTR")
    unresolved["raw_document_path"] = unresolved["raw_document_path"].fillna("")
    return _prepare_review(unresolved[REVIEW_COLUMNS]), "derived:transactions"


def _format_currency(value: float) -> str:
    if pd.isna(value) or value <= 0:
        return "n/a"
    return f"${value:,.0f}"


def _download_bytes(frame: pd.DataFrame) -> bytes:
    buffer = BytesIO()
    frame.to_csv(buffer, index=False)
    return buffer.getvalue()


def _inject_styles() -> None:
    css = """
        <style>
        :root {
            --bg: __BG__;
            --bg-panel: __BG_PANEL__;
            --bg-strong: __BG_PANEL_STRONG__;
            --ink: __INK__;
            --ink-soft: __INK_SOFT__;
            --muted: __MUTED__;
            --line: __LINE__;
            --accent: __ACCENT__;
            --accent-deep: __ACCENT_DEEP__;
            --accent-soft: __ACCENT_SOFT__;
            --navy: __NAVY__;
            --teal: __TEAL__;
            --gold: __GOLD__;
            --shadow: __SHADOW__;
            --sidebar-ink: __SIDEBAR_INK__;
            --sidebar-muted: __SIDEBAR_MUTED__;
            --sidebar-border: __SIDEBAR_BORDER__;
            --sidebar-field: __SIDEBAR_FIELD__;
            --sidebar-field-focus: __SIDEBAR_FIELD_FOCUS__;
            --sidebar-card: __SIDEBAR_CARD__;
            --button-ink: __BUTTON_INK__;
        }
        .stApp {
            background:
                radial-gradient(circle at top left, rgba(198, 146, 43, 0.14), transparent 26%),
                radial-gradient(circle at top right, rgba(45, 111, 109, 0.12), transparent 24%),
                linear-gradient(180deg, #f7f2e8 0%, #f2eadf 48%, #ede3d3 100%);
            color: var(--ink);
        }
        .stApp,
        .stApp p,
        .stApp li,
        .stApp label,
        .stApp span,
        .stApp h1,
        .stApp h2,
        .stApp h3,
        .stApp h4,
        .stApp h5,
        .stApp h6,
        [data-testid="stMarkdownContainer"],
        [data-testid="stCaptionContainer"],
        [data-testid="stHeader"] {
            color: var(--ink);
        }
        section.main > div {
            padding-top: 1.25rem;
        }
        [data-testid="stSidebar"] {
            background: __SIDEBAR_BG__;
            border-right: 1px solid var(--sidebar-border);
        }
        [data-testid="stSidebar"] > div {
            background: transparent;
        }
        [data-testid="stSidebarUserContent"] {
            padding-top: 0.35rem;
            padding-bottom: 0.75rem;
        }
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
        [data-testid="stSidebar"] [data-testid="stCaptionContainer"] p,
        [data-testid="stSidebar"] [data-testid="stWidgetLabel"] p,
        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] span,
        [data-testid="stSidebar"] div,
        [data-testid="stSidebar"] small {
            color: var(--sidebar-ink);
        }
        [data-testid="stSidebar"] h1,
        [data-testid="stSidebar"] h2,
        [data-testid="stSidebar"] h3 {
            color: var(--sidebar-ink) !important;
        }
        [data-testid="stSidebar"] .stMarkdown a {
            color: #ffd9bf;
        }
        [data-testid="stSidebar"] .sidebar-intro,
        [data-testid="stSidebar"] .sidebar-summary {
            background: var(--sidebar-card);
            border: 1px solid var(--sidebar-border);
            border-radius: 22px;
            padding: 1rem 1rem 0.95rem 1rem;
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.03);
            margin-bottom: 0.95rem;
        }
        [data-testid="stSidebar"] .sidebar-filters-heading {
            color: var(--sidebar-ink) !important;
            font-size: 0.95rem;
            font-weight: 800;
            letter-spacing: -0.02em;
            margin: 0 0 0.35rem 0;
        }
        [data-testid="stSidebar"] .sidebar-stat-grid-compact {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 0.4rem;
            margin-top: 0.45rem;
        }
        [data-testid="stSidebar"] .sidebar-stat-tiny {
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.06);
            border-radius: 10px;
            padding: 0.38rem 0.45rem;
        }
        [data-testid="stSidebar"] .sidebar-stat-tiny .sidebar-stat-label {
            font-size: 0.62rem !important;
            letter-spacing: 0.06em !important;
        }
        [data-testid="stSidebar"] .sidebar-stat-tiny .sidebar-stat-value {
            font-size: 0.78rem !important;
            line-height: 1.2 !important;
            margin-top: 0.15rem !important;
            word-break: break-word;
        }
        [data-testid="stSidebar"] .sidebar-expander-caption {
            color: var(--sidebar-muted) !important;
            font-size: 0.72rem !important;
            line-height: 1.35 !important;
            margin: 0 0 0.35rem 0 !important;
        }
        [data-testid="stSidebar"] .sidebar-slice-bar {
            display: flex;
            flex-wrap: wrap;
            align-items: baseline;
            gap: 0.35rem 0.55rem;
            background: var(--sidebar-card);
            border: 1px solid var(--sidebar-border);
            border-radius: 12px;
            padding: 0.45rem 0.55rem;
            margin: 0.5rem 0 0.35rem 0;
            color: var(--sidebar-muted) !important;
            font-size: 0.72rem !important;
            line-height: 1.35 !important;
        }
        [data-testid="stSidebar"] .sidebar-slice-bar strong {
            color: var(--sidebar-ink) !important;
            font-weight: 800;
        }
        [data-testid="stSidebar"] .sidebar-slice-bar .sep {
            opacity: 0.35;
            user-select: none;
        }
        [data-testid="stSidebar"] .sidebar-intro-title,
        [data-testid="stSidebar"] .sidebar-summary-title {
            color: var(--sidebar-ink) !important;
            font-size: 1.02rem;
            font-weight: 800;
            letter-spacing: -0.02em;
            margin: 0;
        }
        [data-testid="stSidebar"] .sidebar-intro-copy,
        [data-testid="stSidebar"] .sidebar-summary-copy,
        [data-testid="stSidebar"] .filter-section-copy {
            color: var(--sidebar-muted) !important;
            font-size: 0.86rem;
            line-height: 1.55;
            margin: 0.28rem 0 0 0;
        }
        [data-testid="stSidebar"] .sidebar-stat-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.65rem;
            margin-top: 0.9rem;
        }
        [data-testid="stSidebar"] .sidebar-stat {
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.06);
            border-radius: 16px;
            padding: 0.75rem 0.8rem;
        }
        [data-testid="stSidebar"] .sidebar-stat-label {
            color: var(--sidebar-muted) !important;
            font-size: 0.72rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            font-weight: 700;
        }
        [data-testid="stSidebar"] .sidebar-stat-value {
            color: var(--sidebar-ink) !important;
            font-size: 1.15rem;
            line-height: 1.1;
            font-weight: 800;
            margin-top: 0.28rem;
        }
        [data-testid="stSidebar"] .filter-section-label {
            color: var(--sidebar-ink) !important;
            font-size: 0.82rem;
            font-weight: 800;
            letter-spacing: -0.01em;
            margin: 0.38rem 0 0.08rem 0;
        }
        [data-testid="stSidebar"] .filter-section-label.filter-first {
            margin-top: 0.15rem;
        }
        [data-testid="stSidebar"] .filter-section-copy {
            margin-bottom: 0.2rem;
            font-size: 0.78rem !important;
            line-height: 1.35 !important;
        }
        [data-testid="stSidebar"] .stMultiSelect [data-baseweb="select"] > div {
            min-height: 2.1rem !important;
            max-height: 4.25rem !important;
            overflow-y: auto !important;
            overflow-x: hidden !important;
            align-items: flex-start !important;
        }
        [data-testid="stSidebar"] .stMultiSelect [data-baseweb="select"] [data-baseweb="tag"] {
            margin: 2px 4px 2px 0 !important;
        }
        [data-testid="stSidebar"] [data-baseweb="select"] > div,
        [data-testid="stSidebar"] [data-baseweb="input"] > div,
        [data-testid="stSidebar"] .stDateInput > div > div,
        [data-testid="stSidebar"] .stTextInput > div > div {
            background: var(--sidebar-field) !important;
            border: 1px solid var(--sidebar-border) !important;
            border-radius: 16px !important;
            min-height: 3rem;
            box-shadow: none !important;
            transition: border-color 160ms ease, background 160ms ease, transform 160ms ease;
        }
        [data-testid="stSidebar"] [data-baseweb="select"] > div:hover,
        [data-testid="stSidebar"] [data-baseweb="input"] > div:hover,
        [data-testid="stSidebar"] .stDateInput > div > div:hover,
        [data-testid="stSidebar"] .stTextInput > div > div:hover {
            border-color: rgba(255, 255, 255, 0.2) !important;
            background: var(--sidebar-field-focus) !important;
        }
        [data-testid="stSidebar"] input,
        [data-testid="stSidebar"] textarea,
        [data-testid="stSidebar"] [data-baseweb="select"] input {
            color: var(--sidebar-ink) !important;
            -webkit-text-fill-color: var(--sidebar-ink) !important;
        }
        [data-testid="stSidebar"] input::placeholder,
        [data-testid="stSidebar"] textarea::placeholder {
            color: rgba(241, 232, 220, 0.45) !important;
            -webkit-text-fill-color: rgba(241, 232, 220, 0.45) !important;
        }
        [data-testid="stSidebar"] [data-baseweb="tag"] {
            background: rgba(166, 75, 42, 0.96) !important;
            border-radius: 12px !important;
            border: 1px solid rgba(255, 214, 189, 0.12) !important;
            color: var(--button-ink) !important;
        }
        [data-testid="stSidebar"] [data-baseweb="tag"] span,
        [data-testid="stSidebar"] [data-baseweb="tag"] svg,
        [data-testid="stSidebar"] button svg,
        [data-testid="stSidebar"] [data-baseweb="select"] svg {
            color: var(--sidebar-ink) !important;
            fill: currentColor !important;
        }
        [data-testid="stSidebar"] .stSlider [data-baseweb="slider"] {
            padding-left: 0.15rem;
            padding-right: 0.15rem;
        }
        [data-testid="stSidebar"] .stSlider [data-baseweb="slider"] > div[data-testid="stTickBar"] {
            background: rgba(255, 255, 255, 0.12);
        }
        [data-testid="stSidebar"] .stSlider [role="slider"] {
            background: #ffd8c0 !important;
            border: 2px solid rgba(126, 53, 29, 0.72) !important;
            box-shadow: 0 0 0 4px rgba(166, 75, 42, 0.18);
        }
        [data-testid="stSidebar"] .stSlider [data-baseweb="slider"] > div > div {
            background: linear-gradient(90deg, #d9774d 0%, #a64b2a 100%);
        }
        [data-testid="stSidebar"] .stDateInput,
        [data-testid="stSidebar"] .stTextInput,
        [data-testid="stSidebar"] .stMultiSelect,
        [data-testid="stSidebar"] .stSelectbox,
        [data-testid="stSidebar"] .stSlider {
            margin-bottom: 0.42rem;
        }
        [data-testid="stSidebar"] [data-testid="stExpander"] {
            margin-bottom: 0.35rem;
        }
        [data-testid="stSidebar"] .sidebar-note {
            color: var(--sidebar-muted) !important;
            margin-top: 0.2rem;
            margin-bottom: 0.35rem;
            font-size: 0.72rem !important;
            line-height: 1.35 !important;
        }
        .stButton > button,
        .stDownloadButton > button,
        button[kind="secondary"] {
            background: linear-gradient(180deg, rgba(166, 75, 42, 0.98) 0%, rgba(126, 53, 29, 0.98) 100%);
            color: var(--button-ink) !important;
            border: 1px solid rgba(126, 53, 29, 0.54) !important;
            border-radius: 999px !important;
            padding: 0.62rem 1rem !important;
            font-weight: 700 !important;
            box-shadow: 0 12px 24px rgba(126, 53, 29, 0.16);
        }
        .stButton > button:hover,
        .stDownloadButton > button:hover,
        button[kind="secondary"]:hover {
            transform: translateY(-1px);
            border-color: rgba(126, 53, 29, 0.72) !important;
            filter: brightness(1.04);
        }
        .stButton > button:focus,
        .stDownloadButton > button:focus,
        button[kind="secondary"]:focus {
            box-shadow: 0 0 0 4px rgba(166, 75, 42, 0.16) !important;
        }
        .dashboard-shell {
            background:
                linear-gradient(135deg, rgba(255, 248, 236, 0.98) 0%, rgba(250, 244, 233, 0.92) 55%, rgba(238, 228, 209, 0.88) 100%);
            border: 1px solid rgba(107, 79, 47, 0.12);
            border-radius: 28px;
            padding: 1.7rem 1.7rem 1.45rem 1.7rem;
            box-shadow: var(--shadow);
            margin-bottom: 1.1rem;
            overflow: hidden;
            position: relative;
        }
        .dashboard-shell::after {
            content: "";
            position: absolute;
            inset: auto -3rem -3rem auto;
            width: 14rem;
            height: 14rem;
            background: radial-gradient(circle, rgba(45, 111, 109, 0.16) 0%, rgba(45, 111, 109, 0) 68%);
            pointer-events: none;
        }
        .hero-grid {
            display: grid;
            grid-template-columns: minmax(0, 1.8fr) minmax(16rem, 0.95fr);
            gap: 1rem;
            align-items: end;
        }
        .eyebrow {
            color: var(--accent);
            font-size: 0.76rem;
            font-weight: 800;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            margin-bottom: 0.45rem;
        }
        .hero-title {
            color: var(--ink);
            font-size: 2.8rem;
            line-height: 0.96;
            font-weight: 800;
            letter-spacing: -0.04em;
            margin: 0;
        }
        .hero-copy {
            color: var(--muted);
            font-size: 1rem;
            line-height: 1.7;
            max-width: 48rem;
            margin: 0.8rem 0 0 0;
        }
        .hero-aside {
            background: rgba(32, 52, 74, 0.94);
            color: __HERO_INK__;
            border-radius: 22px;
            padding: 1rem 1.1rem;
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.05);
        }
        .hero-aside-label {
            font-size: 0.72rem;
            text-transform: uppercase;
            letter-spacing: 0.12em;
            color: __HERO_INK_SOFT__;
        }
        .hero-aside-value {
            font-size: 1.7rem;
            font-weight: 800;
            margin: 0.35rem 0 0.6rem 0;
        }
        .hero-meta {
            display: flex;
            flex-wrap: wrap;
            gap: 0.65rem;
            margin-top: 1rem;
        }
        .meta-pill {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            padding: 0.44rem 0.78rem;
            border-radius: 999px;
            background: rgba(32, 52, 74, 0.08);
            border: 1px solid rgba(32, 52, 74, 0.08);
            color: var(--navy);
            font-size: 0.83rem;
            font-weight: 700;
        }
        .metric-card {
            background: rgba(255, 250, 241, 0.88);
            border: 1px solid rgba(48, 58, 71, 0.10);
            border-radius: 22px;
            padding: 1rem 1.1rem;
            box-shadow: 0 14px 32px rgba(45, 35, 24, 0.06);
            min-height: 8.1rem;
        }
        .metric-card.accent {
            background: linear-gradient(180deg, rgba(166, 75, 42, 0.97) 0%, rgba(126, 53, 29, 0.96) 100%);
            color: __HERO_INK__;
            border-color: rgba(126, 53, 29, 0.40);
        }
        .metric-label {
            font-size: 0.76rem;
            font-weight: 800;
            letter-spacing: 0.09em;
            text-transform: uppercase;
            color: #6f7780;
            margin-bottom: 0.55rem;
        }
        .metric-card.accent .metric-label,
        .metric-card.accent .metric-subtle {
            color: __HERO_INK_SOFT__;
        }
        .metric-value {
            font-size: 2rem;
            line-height: 1;
            font-weight: 800;
            letter-spacing: -0.04em;
            color: var(--ink);
            margin-bottom: 0.45rem;
        }
        .metric-card.accent .metric-value {
            color: __HERO_INK__;
        }
        .metric-subtle {
            color: var(--muted);
            font-size: 0.92rem;
            line-height: 1.45;
        }
        .section-card {
            background: var(--bg-panel);
            border: 1px solid var(--line);
            border-radius: 24px;
            padding: 1rem 1rem 0.65rem 1rem;
            box-shadow: 0 14px 34px rgba(45, 35, 24, 0.05);
            margin-bottom: 1rem;
        }
        .section-kicker {
            color: var(--accent);
            font-size: 0.76rem;
            font-weight: 800;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            margin-bottom: 0.2rem;
        }
        .section-title {
            color: var(--ink);
            font-size: 1.2rem;
            font-weight: 800;
            margin: 0 0 0.2rem 0;
        }
        .section-copy {
            color: var(--muted);
            font-size: 0.94rem;
            margin-bottom: 0.65rem;
        }
        div[data-testid="stDataFrame"] {
            border: 1px solid rgba(48, 58, 71, 0.12);
            border-radius: 18px;
            overflow: hidden;
            background: rgba(255, 250, 241, 0.72);
        }
        button[kind="secondary"] {
            border-radius: 999px;
            border: 1px solid rgba(32, 52, 74, 0.12);
        }
        .stTabs [data-baseweb="tab-list"] {
            gap: 0.4rem;
        }
        .stTabs [data-baseweb="tab"] {
            background: rgba(255, 250, 241, 0.72);
            border: 1px solid rgba(48, 58, 71, 0.10);
            border-radius: 999px;
            padding: 0.3rem 0.95rem;
            height: auto;
            color: var(--ink);
        }
        .stTabs [data-baseweb="tab"] * {
            color: var(--ink);
        }
        .stTabs [aria-selected="true"] {
            background: rgba(166, 75, 42, 0.10);
            color: var(--accent-deep);
        }
        .stTabs [aria-selected="true"] * {
            color: var(--accent-deep);
        }
        .stAlert {
            color: var(--ink);
        }
        h2, h3 {
            color: var(--ink);
        }
        @media (max-width: 980px) {
            .hero-grid {
                grid-template-columns: 1fr;
            }
            .hero-title {
                font-size: 2.2rem;
            }
        }
        </style>
    """
    css = (
        css.replace("__BG__", THEME["bg"])
        .replace("__BG_PANEL__", THEME["bg_panel"])
        .replace("__BG_PANEL_STRONG__", THEME["bg_panel_strong"])
        .replace("__INK__", THEME["ink"])
        .replace("__INK_SOFT__", THEME["ink_soft"])
        .replace("__MUTED__", THEME["muted"])
        .replace("__LINE__", THEME["line"])
        .replace("__ACCENT__", THEME["accent"])
        .replace("__ACCENT_DEEP__", THEME["accent_deep"])
        .replace("__ACCENT_SOFT__", THEME["accent_soft"])
        .replace("__NAVY__", THEME["navy"])
        .replace("__TEAL__", THEME["teal"])
        .replace("__GOLD__", THEME["gold"])
        .replace("__SHADOW__", THEME["shadow"])
        .replace("__SIDEBAR_BG__", THEME["sidebar_bg"])
        .replace("__SIDEBAR_INK__", THEME["sidebar_ink"])
        .replace("__SIDEBAR_MUTED__", THEME["sidebar_muted"])
        .replace("__SIDEBAR_BORDER__", THEME["sidebar_border"])
        .replace("__SIDEBAR_FIELD__", THEME["sidebar_field"])
        .replace("__SIDEBAR_FIELD_FOCUS__", THEME["sidebar_field_focus"])
        .replace("__SIDEBAR_CARD__", THEME["sidebar_card"])
        .replace("__BUTTON_INK__", THEME["button_ink"])
        .replace("__HERO_INK__", THEME["hero_ink"])
        .replace("__HERO_INK_SOFT__", THEME["hero_ink_soft"])
    )
    st.markdown(
        css,
        unsafe_allow_html=True,
    )


def _copy(key: str) -> str:
    return DASHBOARD_COPY[key]


def _metric_card(label: str, value: str, detail: str, *, accent: bool = False) -> str:
    tone = "metric-card accent" if accent else "metric-card"
    return f"""
    <div class=\"{tone}\">
        <div class=\"metric-label\">{label}</div>
        <div class=\"metric-value\">{value}</div>
        <div class=\"metric-subtle\">{detail}</div>
    </div>
    """


def _render_section_intro(kicker: str, title: str, copy: str) -> None:
    st.markdown(
        f"""
        <div class=\"section-card\">
            <div class=\"section-kicker\">{kicker}</div>
            <div class=\"section-title\">{title}</div>
            <div class=\"section-copy\">{copy}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_hero(
    *,
    transaction_source: str,
    review_source: str,
    total_transactions: int | None = None,
    tracked_tickers: int | None = None,
    open_reviews: int | None = None,
    avg_confidence: float | None = None,
    active_chambers: str | None = None,
    coverage_label: str | None = None,
    latest_filing_label: str | None = None,
    empty: bool = False,
) -> None:
    if empty:
        st.markdown(
            f"""
            <section class="dashboard-shell">
                <div class="eyebrow">{_copy("eyebrow")}</div>
                <h1 class="hero-title">{_copy("empty_hero_title")}</h1>
                <p class="hero-copy">{_copy("empty_hero_copy")}</p>
                <div class="hero-meta">
                    <div class="meta-pill">Transactions source: {transaction_source}</div>
                    <div class="meta-pill">Review source: {review_source}</div>
                </div>
            </section>
            """,
            unsafe_allow_html=True,
        )
        return

    st.markdown(
        f"""
        <section class="dashboard-shell">
            <div class="hero-grid">
                <div>
                    <div class="eyebrow">{_copy("eyebrow")}</div>
                    <h1 class="hero-title">{_copy("hero_title")}</h1>
                    <p class="hero-copy">{_copy("hero_copy")}</p>
                    <div class="hero-meta">
                        <div class="meta-pill">Visible chambers: {active_chambers}</div>
                        <div class="meta-pill">Transaction coverage: {coverage_label}</div>
                        <div class="meta-pill">Transactions source: {transaction_source}</div>
                        <div class="meta-pill">Review source: {review_source}</div>
                    </div>
                </div>
                <div class="hero-aside">
                    <div class="hero-aside-label">{_copy("current_slice")}</div>
                    <div class="hero-aside-value">{total_transactions:,} trades</div>
                    <div>Latest filing: {latest_filing_label}</div>
                    <div style="margin-top:0.35rem; color: {THEME['hero_ink_soft']};">
                        {open_reviews:,} open review items, {tracked_tickers:,} resolved tickers, {avg_confidence:.0%} average confidence.
                    </div>
                </div>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def _build_time_series_chart(frame: pd.DataFrame) -> alt.Chart:
    chart_data = frame.copy()
    chart_data["month_label"] = chart_data["month"].dt.strftime("%b %Y")

    return (
        alt.Chart(chart_data)
        .mark_area(line={"color": THEME["accent"], "strokeWidth": 3}, color="#d7a869", opacity=0.35)
        .encode(
            x=alt.X("month:T", axis=alt.Axis(title=None, labelColor=THEME["muted"], grid=False)),
            y=alt.Y("transactions:Q", axis=alt.Axis(title="Transactions", labelColor=THEME["muted"], tickCount=5, gridColor=THEME["chart_grid"])),
            tooltip=[
                alt.Tooltip("month_label:N", title="Month"),
                alt.Tooltip("transactions:Q", title="Transactions", format=",.0f"),
                alt.Tooltip("estimated_value:Q", title="Estimated Midpoint", format="$,.0f"),
            ],
        )
        .properties(height=280)
        .configure(background="transparent")
        .configure_view(stroke=None)
    )


def _build_rank_chart(frame: pd.DataFrame, label_field: str, title: str, *, color: str) -> alt.Chart:
    chart_data = frame.copy()
    chart_data = chart_data.sort_values("transactions", ascending=False)

    return (
        alt.Chart(chart_data)
        .mark_bar(cornerRadiusTopRight=6, cornerRadiusBottomRight=6, color=color)
        .encode(
            x=alt.X("transactions:Q", axis=alt.Axis(title=title, labelColor=THEME["muted"], tickCount=5, gridColor=THEME["chart_grid"])),
            y=alt.Y(f"{label_field}:N", sort="-x", axis=alt.Axis(title=None, labelColor=THEME["ink_soft"], labelLimit=180)),
            tooltip=[
                alt.Tooltip(f"{label_field}:N", title=title.rstrip("s")),
                alt.Tooltip("transactions:Q", title="Transactions", format=",.0f"),
                alt.Tooltip("estimated_value:Q", title="Estimated Midpoint", format="$,.0f"),
            ],
        )
        .properties(height=320)
        .configure(background="transparent")
        .configure_view(stroke=None)
    )


def _build_mix_chart(frame: pd.DataFrame, label_field: str, *, color: str) -> alt.Chart:
    chart_data = frame.copy()
    return (
        alt.Chart(chart_data)
        .mark_bar(cornerRadiusTopLeft=8, cornerRadiusTopRight=8, color=color)
        .encode(
            x=alt.X(f"{label_field}:N", axis=alt.Axis(title=None, labelColor=THEME["ink_soft"], labelAngle=0)),
            y=alt.Y("transactions:Q", axis=alt.Axis(title="Transactions", labelColor=THEME["muted"], tickCount=4, gridColor=THEME["chart_grid"])),
            tooltip=[
                alt.Tooltip(f"{label_field}:N", title=label_field.replace("_", " ").title()),
                alt.Tooltip("transactions:Q", title="Transactions", format=",.0f"),
            ],
        )
        .properties(height=250)
        .configure(background="transparent")
        .configure_view(stroke=None)
    )


def _build_ticker_member_timeline(frame: pd.DataFrame, ticker: str) -> alt.Chart | None:
    if not ticker or not str(ticker).strip():
        return None
    t = str(ticker).strip().upper()
    sub = frame[frame["ticker"].astype(str).str.upper() == t].copy()
    sub = sub.dropna(subset=["transaction_date"])
    if sub.empty:
        return None
    member_order = (
        sub.groupby("member", observed=True)["transaction_date"]
        .max()
        .sort_values(ascending=False)
        .index.tolist()
    )
    height = min(520, max(220, 32 * max(6, len(member_order))))
    return (
        alt.Chart(sub)
        .mark_circle(size=88, opacity=0.78)
        .encode(
            x=alt.X(
                "transaction_date:T",
                title="Transaction date",
                axis=alt.Axis(labelColor=THEME["muted"], gridColor=THEME["chart_grid"]),
            ),
            y=alt.Y(
                "member:N",
                title=None,
                sort=member_order,
                axis=alt.Axis(labelColor=THEME["ink_soft"], labelLimit=220),
            ),
            color=alt.Color(
                "transaction_type:N",
                legend=alt.Legend(title="Type"),
                scale=alt.Scale(range=[THEME["teal"], THEME["accent"], THEME["navy"], THEME["gold"]]),
            ),
            tooltip=[
                alt.Tooltip("member:N", title="Member"),
                alt.Tooltip("transaction_date:T", title="Date", format="%Y-%m-%d"),
                alt.Tooltip("transaction_type:N", title="Type"),
                alt.Tooltip("amount_range_raw:N", title="Amount range"),
                alt.Tooltip("issuer_name:N", title="Issuer"),
                alt.Tooltip("chamber:N", title="Chamber"),
            ],
        )
        .properties(height=height)
        .configure(background="transparent")
        .configure_view(stroke=None)
    )


def _sidebar_full_dataset_stats_compact(data: pd.DataFrame) -> None:
    transaction_count = len(data)
    member_count = data["member"].nunique()
    ticker_count = data.loc[data["ticker"] != "", "ticker"].nunique()
    valid_dates = data["transaction_date"].dropna()
    coverage = _copy("no_dated_trades")
    if not valid_dates.empty:
        coverage = f"{valid_dates.min():%Y-%m-%d} → {valid_dates.max():%Y-%m-%d}"

    st.markdown(
        f"""
        <div class="sidebar-stat-grid-compact">
            <div class="sidebar-stat-tiny">
                <div class="sidebar-stat-label">Txns</div>
                <div class="sidebar-stat-value">{transaction_count:,}</div>
            </div>
            <div class="sidebar-stat-tiny">
                <div class="sidebar-stat-label">Members</div>
                <div class="sidebar-stat-value">{member_count:,}</div>
            </div>
            <div class="sidebar-stat-tiny">
                <div class="sidebar-stat-label">Tickers</div>
                <div class="sidebar-stat-value">{ticker_count:,}</div>
            </div>
            <div class="sidebar-stat-tiny">
                <div class="sidebar-stat-label">Dates</div>
                <div class="sidebar-stat-value">{coverage}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _sidebar_filter_label(title: str, copy: str = "", *, first: bool = False) -> None:
    extra = " filter-first" if first else ""
    if copy:
        st.sidebar.markdown(
            f"""
            <div class="filter-section-label{extra}">{title}</div>
            <div class="filter-section-copy">{copy}</div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.sidebar.markdown(
            f'<div class="filter-section-label{extra}">{title}</div>',
            unsafe_allow_html=True,
        )


def _sidebar_slice_bar(filtered: pd.DataFrame) -> None:
    visible_records = len(filtered)
    visible_members = filtered["member"].nunique()
    avg_confidence = filtered["confidence_score"].mean() if visible_records else 0.0
    unresolved = int((filtered["review_status"] != "resolved").sum()) if visible_records else 0
    title = _copy("sidebar_slice_summary_title")
    st.sidebar.markdown(
        f"""
        <div class="sidebar-slice-bar">
            <span><strong>{title}</strong> {visible_records:,} rows</span>
            <span class="sep">·</span>
            <span>{visible_members:,} members</span>
            <span class="sep">·</span>
            <span>{avg_confidence:.0%} avg conf.</span>
            <span class="sep">·</span>
            <span>{unresolved:,} need review</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _apply_filters(data: pd.DataFrame) -> pd.DataFrame:
    """Scope first (dates, chamber), then pick lists (member, ticker, issuer), facets, confidence."""
    filtered = data.copy()
    st.sidebar.markdown(
        f'<p class="sidebar-filters-heading">{_copy("sidebar_header")}</p>',
        unsafe_allow_html=True,
    )
    with st.sidebar.expander(_copy("sidebar_dataset_expander"), expanded=False):
        st.markdown(
            f'<p class="sidebar-expander-caption">{_copy("sidebar_dataset_expander_caption")}</p>',
            unsafe_allow_html=True,
        )
        _sidebar_full_dataset_stats_compact(data)

    first_label = True

    valid_dates = filtered["transaction_date"].dropna()
    if not valid_dates.empty:
        min_date = valid_dates.min().date()
        max_date = valid_dates.max().date()
        today = date.today()
        picker_max = max(max_date, today)
        default_start = max(min_date, DEFAULT_TRANSACTION_FILTER_START)
        default_end = min(max_date, today)
        if default_start > default_end:
            default_start, default_end = min_date, max_date
        _sidebar_filter_label("Transaction dates", first=first_label)
        first_label = False
        date_range = st.sidebar.date_input(
            "Transaction Date Range",
            value=(default_start, default_end),
            min_value=min_date,
            max_value=picker_max,
            label_visibility="collapsed",
            key="sidebar_transaction_date_filter",
        )
        if isinstance(date_range, tuple) and len(date_range) == 2:
            start_date, end_date = date_range
            filtered = filtered[
                filtered["transaction_date"].between(pd.Timestamp(start_date), pd.Timestamp(end_date))
            ]

    chambers = sorted(value for value in filtered["chamber"].dropna().astype(str).unique() if value)
    if chambers:
        _sidebar_filter_label("Chamber", first=first_label)
        first_label = False
        selected_chambers = st.sidebar.multiselect(
            "Chamber",
            chambers,
            default=chambers,
            label_visibility="collapsed",
            key="sidebar_chamber_filter",
        )
        filtered = filtered[filtered["chamber"].isin(selected_chambers)]

    members_sorted = sorted({str(m).strip() for m in filtered["member"].dropna().unique() if str(m).strip()})
    if members_sorted:
        _sidebar_filter_label(_copy("sidebar_pick_member_label"), first=first_label)
        first_label = False
        member_options = [_SIDEBAR_ANY, *members_sorted]
        member_choice = st.sidebar.selectbox(
            "Member",
            member_options,
            label_visibility="collapsed",
            key="sidebar_pick_member",
        )
        if member_choice != _SIDEBAR_ANY:
            mcol = filtered["member"].astype(str).str.strip()
            filtered = filtered[mcol == member_choice]

    tickers_nonempty = sorted(
        {str(t).strip() for t in filtered["ticker"].dropna().unique() if str(t).strip()}
    )
    has_blank_ticker = filtered["ticker"].fillna("").astype(str).str.strip().eq("").any()
    ticker_options = [_SIDEBAR_ANY]
    if has_blank_ticker:
        ticker_options.append(_SIDEBAR_NO_TICKER)
    ticker_options.extend(tickers_nonempty)
    if len(ticker_options) > 1:
        _sidebar_filter_label(_copy("sidebar_pick_ticker_label"), first=first_label)
        first_label = False
        ticker_choice = st.sidebar.selectbox(
            "Ticker",
            ticker_options,
            label_visibility="collapsed",
            key="sidebar_pick_ticker",
        )
        if ticker_choice == _SIDEBAR_NO_TICKER:
            filtered = filtered[filtered["ticker"].fillna("").astype(str).str.strip().eq("")]
        elif ticker_choice != _SIDEBAR_ANY:
            tcol = filtered["ticker"].fillna("").astype(str).str.strip()
            filtered = filtered[tcol == ticker_choice]

    issuers_nonempty = sorted(
        {str(i).strip() for i in filtered["issuer_name"].dropna().unique() if str(i).strip()}
    )
    has_blank_issuer = filtered["issuer_name"].fillna("").astype(str).str.strip().eq("").any()
    issuer_options: list[str] = []
    if has_blank_issuer:
        issuer_options.append(_SIDEBAR_NO_ISSUER)
    issuer_options.extend(issuers_nonempty)
    if issuer_options:
        _sidebar_filter_label(_copy("sidebar_pick_issuer_label"), first=first_label)
        first_label = False
        issuer_pick = st.sidebar.multiselect(
            "Issuer",
            issuer_options,
            default=[],
            label_visibility="collapsed",
            key="sidebar_pick_issuer",
            help="Leave empty for all issuers. Pick one or more; type in the box to search the list.",
        )
        if issuer_pick:
            icol = filtered["issuer_name"].fillna("").astype(str).str.strip()
            parts: list[pd.Series] = []
            if _SIDEBAR_NO_ISSUER in issuer_pick:
                parts.append(icol.eq(""))
            rest = [x for x in issuer_pick if x != _SIDEBAR_NO_ISSUER]
            if rest:
                parts.append(icol.isin(rest))
            if parts:
                combined = parts[0]
                for p in parts[1:]:
                    combined = combined | p
                filtered = filtered[combined]

    transaction_types = sorted(value for value in filtered["transaction_type"].dropna().astype(str).unique() if value)
    if transaction_types:
        _sidebar_filter_label("Transaction type")
        selected_types = st.sidebar.multiselect(
            "Transaction Type",
            transaction_types,
            default=transaction_types,
            label_visibility="collapsed",
            key="sidebar_transaction_type_filter",
        )
        filtered = filtered[filtered["transaction_type"].isin(selected_types)]

    asset_types = sorted(value for value in filtered["asset_type"].dropna().astype(str).unique() if value)
    if asset_types:
        _sidebar_filter_label("Asset type")
        selected_asset_types = st.sidebar.multiselect(
            "Asset Type",
            asset_types,
            default=asset_types,
            label_visibility="collapsed",
            key="sidebar_asset_type_filter",
        )
        filtered = filtered[filtered["asset_type"].isin(selected_asset_types)]

    review_statuses = sorted(value for value in filtered["review_status"].dropna().astype(str).unique() if value)
    if review_statuses:
        _sidebar_filter_label("Review status")
        selected_statuses = st.sidebar.multiselect(
            "Review Status",
            review_statuses,
            default=review_statuses,
            label_visibility="collapsed",
            key="sidebar_review_status_filter",
        )
        filtered = filtered[filtered["review_status"].isin(selected_statuses)]

    _sidebar_filter_label("Minimum confidence (0–1)")
    confidence_threshold = st.sidebar.slider(
        "Minimum Confidence",
        min_value=0.0,
        max_value=1.0,
        value=0.0,
        step=0.05,
        label_visibility="collapsed",
        key="sidebar_confidence_filter",
    )
    filtered = filtered[filtered["confidence_score"] >= confidence_threshold]

    _sidebar_slice_bar(filtered)
    return filtered


def _render_empty_state() -> None:
    st.warning(_copy("empty_state"))
    st.code(
        "\n".join(
            [
                "python -m src.main ingest-all",
                "python -m src.main export-csv --out data/congress_trades.csv",
                "python -m src.main dashboard",
            ]
        ),
        language="bash",
    )


def _filter_review_queue(review_queue: pd.DataFrame, filtered_transactions: pd.DataFrame) -> pd.DataFrame:
    if review_queue.empty or filtered_transactions.empty:
        return review_queue.iloc[0:0].copy()

    review_index = review_queue.assign(
        _review_key=(
            review_queue["member"].astype(str)
            + "|"
            + review_queue["asset_name_raw"].astype(str)
            + "|"
            + review_queue["transaction_type"].astype(str)
            + "|"
            + review_queue["amount_range_raw"].astype(str)
            + "|"
            + review_queue["transaction_date"].astype(str)
        )
    )
    filtered_index = filtered_transactions.assign(
        _review_key=(
            filtered_transactions["member"].astype(str)
            + "|"
            + filtered_transactions["asset_name_raw"].astype(str)
            + "|"
            + filtered_transactions["transaction_type"].astype(str)
            + "|"
            + filtered_transactions["amount_range_raw"].astype(str)
            + "|"
            + filtered_transactions["transaction_date"].astype(str)
        )
    )
    return review_index[review_index["_review_key"].isin(filtered_index["_review_key"])].drop(columns=["_review_key"])


def render_dashboard() -> None:
    st.set_page_config(
        page_title=_copy("page_title"),
        page_icon="/",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _inject_styles()

    transactions, transaction_source = load_transactions()
    review_queue, review_source = load_review_queue(transactions)

    if transactions.empty:
        _render_hero(transaction_source=transaction_source, review_source=review_source, empty=True)
        _render_empty_state()
        return

    filtered = _apply_filters(transactions)
    filtered_review = _filter_review_queue(review_queue, filtered)

    total_transactions = len(filtered)
    total_members = filtered["member"].nunique()
    tracked_tickers = filtered.loc[filtered["ticker"] != "", "ticker"].nunique()
    open_reviews = int((filtered_review["status"] == "open").sum()) if not filtered_review.empty else 0
    estimated_value = filtered["estimated_value"].sum(skipna=True)
    avg_confidence = filtered["confidence_score"].mean() if total_transactions else 0.0
    active_chambers = ", ".join(sorted(filtered["chamber"].dropna().astype(str).unique())) or _copy("no_chamber_selected")
    latest_filing = filtered["filing_date"].max()
    visible_date_min = filtered["transaction_date"].min()
    visible_date_max = filtered["transaction_date"].max()
    coverage_label = _copy("no_dated_trades")
    latest_filing_label = "n/a"
    if pd.notna(visible_date_min) and pd.notna(visible_date_max):
        coverage_label = f"{visible_date_min:%Y-%m-%d} to {visible_date_max:%Y-%m-%d}"
    if pd.notna(latest_filing):
        latest_filing_label = f"{latest_filing:%Y-%m-%d}"

    _render_hero(
        transaction_source=transaction_source,
        review_source=review_source,
        total_transactions=total_transactions,
        tracked_tickers=tracked_tickers,
        open_reviews=open_reviews,
        avg_confidence=avg_confidence,
        active_chambers=active_chambers,
        coverage_label=coverage_label,
        latest_filing_label=latest_filing_label,
    )

    metric_columns = st.columns(5)
    metric_columns[0].markdown(
        _metric_card("Transactions", f"{total_transactions:,}", "Rows currently visible after filters."),
        unsafe_allow_html=True,
    )
    metric_columns[1].markdown(
        _metric_card("Members", f"{total_members:,}", "Distinct filers represented in the visible slice."),
        unsafe_allow_html=True,
    )
    metric_columns[2].markdown(
        _metric_card("Tickers", f"{tracked_tickers:,}", "Resolved instruments ready for analysis."),
        unsafe_allow_html=True,
    )
    metric_columns[3].markdown(
        _metric_card("Open Reviews", f"{open_reviews:,}", "Records still flagged for manual validation."),
        unsafe_allow_html=True,
    )
    metric_columns[4].markdown(
        _metric_card("Estimated Midpoint", _format_currency(estimated_value), f"Average confidence {avg_confidence:.0%}.", accent=True),
        unsafe_allow_html=True,
    )

    overview_tab, review_tab, raw_tab = st.tabs([_copy("tab_overview"), _copy("tab_review"), _copy("tab_raw")])

    with overview_tab:
        latest_transactions = filtered.sort_values(
            ["transaction_date", "filing_date"],
            ascending=[False, False],
        ).head(50)
        st.subheader(_copy("sub_latest_transactions"))
        st.dataframe(
            latest_transactions[
                [
                    "transaction_date",
                    "member",
                    "chamber",
                    "issuer_name",
                    "ticker",
                    "transaction_type",
                    "amount_range_raw",
                    "confidence_score",
                    "review_status",
                ]
            ],
            hide_index=True,
            width="stretch",
            height=420,
            column_config={
                "transaction_date": st.column_config.DateColumn("Transaction Date", format="YYYY-MM-DD"),
                "confidence_score": st.column_config.ProgressColumn(
                    "Confidence",
                    format="%.2f",
                    min_value=0.0,
                    max_value=1.0,
                ),
            },
        )

        st.subheader(_copy("sub_ticker_who_when"))
        st.caption(_copy("ticker_chart_caption"))
        tickers_available = sorted(
            x for x in filtered.loc[filtered["ticker"].astype(str) != "", "ticker"].astype(str).unique() if x
        )
        if not tickers_available:
            st.info(
                "No resolved tickers in the current slice. Widen filters, set the sidebar Member or Ticker "
                "dropdown to **Any**, or pick a different issuer; many disclosures still lack ticker mapping."
            )
        else:
            pick_col, override_col = st.columns([1, 1])
            with pick_col:
                selected_ticker = st.selectbox(
                    "Ticker",
                    tickers_available,
                    label_visibility="collapsed",
                    key="overview_ticker_timeline_pick",
                )
            with override_col:
                manual = st.text_input(
                    "Ticker override (optional)",
                    placeholder="e.g. MSFT",
                    key="overview_ticker_manual",
                ).strip().upper()
            ticker_for_chart = manual if manual else selected_ticker
            ticker_chart = _build_ticker_member_timeline(filtered, ticker_for_chart)
            if ticker_chart is None:
                st.info(f"No transactions for ticker **{ticker_for_chart}** in the current slice.")
            else:
                st.altair_chart(ticker_chart, width="stretch")

        _render_section_intro(
            _copy("overview_kicker"),
            _copy("overview_title"),
            _copy("overview_copy"),
        )
        monthly_activity = (
            filtered.dropna(subset=["month"])
            .groupby("month", as_index=False)
            .agg(transactions=("member", "size"), estimated_value=("estimated_value", "sum"))
            .sort_values("month")
        )
        chamber_mix = (
            filtered.groupby("chamber", as_index=False)
            .size()
            .rename(columns={"size": "transactions"})
            .sort_values("transactions", ascending=False)
        )
        transaction_mix = (
            filtered.groupby("transaction_type", as_index=False)
            .size()
            .rename(columns={"size": "transactions"})
            .sort_values("transactions", ascending=False)
        )
        top_members = (
            filtered.groupby("member", as_index=False)
            .agg(transactions=("member", "size"), estimated_value=("estimated_value", "sum"))
            .sort_values(["transactions", "estimated_value"], ascending=[False, False])
            .head(10)
        )
        top_tickers = (
            filtered.loc[filtered["ticker"] != ""]
            .groupby("ticker", as_index=False)
            .agg(transactions=("ticker", "size"), estimated_value=("estimated_value", "sum"))
            .sort_values(["transactions", "estimated_value"], ascending=[False, False])
            .head(10)
        )

        left, right = st.columns([1.4, 1])
        with left:
            st.subheader(_copy("sub_monthly_activity"))
            if monthly_activity.empty:
                st.info("No valid transaction dates in the current filter.")
            else:
                st.altair_chart(_build_time_series_chart(monthly_activity), width="stretch")

            st.subheader(_copy("sub_top_members"))
            if top_members.empty:
                st.info("No member activity for the current filter.")
            else:
                st.altair_chart(
                    _build_rank_chart(top_members, "member", "Transactions", color=THEME["navy"]),
                    width="stretch",
                )
                st.dataframe(
                    top_members,
                    hide_index=True,
                    width="stretch",
                    height=320,
                    column_config={
                        "estimated_value": st.column_config.NumberColumn("Estimated Midpoint", format="$%d"),
                    },
                )

        with right:
            st.subheader(_copy("sub_chamber_mix"))
            if chamber_mix.empty:
                st.info("No chamber distribution for the current filter.")
            else:
                st.altair_chart(_build_mix_chart(chamber_mix, "chamber", color=THEME["teal"]), width="stretch")

            st.subheader(_copy("sub_transaction_type_mix"))
            if transaction_mix.empty:
                st.info("No transaction-type distribution for the current filter.")
            else:
                st.altair_chart(_build_mix_chart(transaction_mix, "transaction_type", color=THEME["accent"]), width="stretch")

            st.subheader(_copy("sub_top_tickers"))
            if top_tickers.empty:
                st.info("No resolved tickers in the current filter.")
            else:
                st.altair_chart(
                    _build_rank_chart(top_tickers, "ticker", "Transactions", color=THEME["gold"]),
                    width="stretch",
                )
                st.dataframe(
                    top_tickers,
                    hide_index=True,
                    width="stretch",
                    height=320,
                    column_config={
                        "estimated_value": st.column_config.NumberColumn("Estimated Midpoint", format="$%d"),
                    },
                )

    with review_tab:
        _render_section_intro(
            _copy("review_kicker"),
            _copy("review_title"),
            _copy("review_copy"),
        )
        st.subheader(_copy("sub_records_needing_review"))
        if filtered_review.empty:
            st.success("No records currently require review for the selected filter.")
        else:
            review_reason_counts = (
                filtered_review.groupby("reason", as_index=False)
                .size()
                .rename(columns={"size": "records"})
                .sort_values("records", ascending=False)
            )
            review_status_counts = (
                filtered_review.groupby("status", as_index=False)
                .size()
                .rename(columns={"size": "records"})
                .sort_values("records", ascending=False)
            )
            review_cols = st.columns(2)
            review_cols[0].altair_chart(_build_mix_chart(review_reason_counts.rename(columns={"records": "transactions"}), "reason", color=THEME["navy"]), width="stretch")
            review_cols[1].altair_chart(_build_mix_chart(review_status_counts.rename(columns={"records": "transactions"}), "status", color=THEME["accent"]), width="stretch")
            st.dataframe(
                filtered_review.sort_values(["transaction_date", "filing_date"], ascending=[False, False]),
                hide_index=True,
                width="stretch",
                height=520,
                column_config={
                    "transaction_date": st.column_config.DateColumn("Transaction Date", format="YYYY-MM-DD"),
                    "filing_date": st.column_config.DateColumn("Filing Date", format="YYYY-MM-DD"),
                    "confidence_score": st.column_config.ProgressColumn(
                        "Confidence",
                        format="%.2f",
                        min_value=0.0,
                        max_value=1.0,
                    ),
                },
            )

    with raw_tab:
        _render_section_intro(
            _copy("raw_kicker"),
            _copy("raw_title"),
            _copy("raw_copy"),
        )
        st.subheader(_copy("sub_filtered_dataset"))
        st.download_button(
            label="Download filtered transactions as CSV",
            data=_download_bytes(filtered),
            file_name="congress_transactions_filtered.csv",
            mime="text/csv",
        )
        st.dataframe(
            filtered.sort_values(["transaction_date", "filing_date"], ascending=[False, False]),
            hide_index=True,
            width="stretch",
            height=620,
            column_config={
                "transaction_date": st.column_config.DateColumn("Transaction Date", format="YYYY-MM-DD"),
                "filing_date": st.column_config.DateColumn("Filing Date", format="YYYY-MM-DD"),
                "amount_low": st.column_config.NumberColumn("Amount Low", format="$%d"),
                "amount_high": st.column_config.NumberColumn("Amount High", format="$%d"),
                "estimated_value": st.column_config.NumberColumn("Estimated Midpoint", format="$%d"),
                "confidence_score": st.column_config.ProgressColumn(
                    "Confidence",
                    format="%.2f",
                    min_value=0.0,
                    max_value=1.0,
                ),
            },
        )