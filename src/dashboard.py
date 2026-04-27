from __future__ import annotations

from datetime import date
from io import BytesIO
from pathlib import Path
import re
import sqlite3

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from .config import DATA_DIR, DB_PATH, HOUSE_PTR_PDF_URL
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


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _polygon_daily_bar_cache_size(conn: sqlite3.Connection) -> int:
    if not _table_exists(conn, "polygon_daily_bar_cache"):
        return 0
    try:
        return int(conn.execute("SELECT COUNT(*) FROM polygon_daily_bar_cache").fetchone()[0])
    except sqlite3.Error:
        return 0


def merge_polygon_pnl_cached_columns(frame: pd.DataFrame, *, as_of: date | None = None) -> pd.DataFrame:
    """Append Polygon estimate columns using only `polygon_daily_bar_cache` (no HTTP from the dashboard)."""
    from .polygon_prices import POLYGON_PNL_EXTRA_COLUMNS, enrich_export_rows_with_polygon_pnl

    if frame.empty:
        return frame
    a = as_of or date.today()
    conn = get_connection()
    try:
        init_db(conn)
        if _polygon_daily_bar_cache_size(conn) == 0:
            return frame
        enriched = enrich_export_rows_with_polygon_pnl(
            conn,
            frame.to_dict("records"),
            as_of=a,
            api_key="",
            force_refetch=False,
            cache_only=True,
        )
    finally:
        conn.close()
    out = frame.copy()
    for col in POLYGON_PNL_EXTRA_COLUMNS:
        out[col] = [r.get(col, "") for r in enriched]
    return out


def _empty_frame(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=columns)


def _read_sqlite(query: str) -> pd.DataFrame:
    conn = get_connection()
    try:
        init_db(conn)
        return pd.read_sql_query(query, conn)
    finally:
        conn.close()


def _house_ptr_year_from_raw_path(raw_document_path: str) -> int | None:
    if not raw_document_path:
        return None
    try:
        parent = Path(raw_document_path).parent.name
        if parent.isdigit() and len(parent) == 4:
            y = int(parent)
            if 1990 <= y <= 2100:
                return y
    except (OSError, ValueError):
        pass
    return None


def _compute_disclosure_url_row(row: pd.Series) -> str:
    """Best URL for the originating disclosure PDF (House PTR on clerk.house.gov when inferable)."""
    su = row.get("source_url")
    if pd.notna(su) and str(su).strip():
        return str(su).strip()
    chamber = str(row.get("chamber") or "").strip().lower()
    if chamber != "house":
        return ""
    raw_path = str(row.get("raw_document_path") or "").strip()
    doc_id = str(row.get("doc_id") or "").strip()
    if not doc_id and raw_path:
        try:
            doc_id = Path(raw_path).stem
        except (OSError, ValueError):
            doc_id = ""
    if not doc_id:
        return ""
    year = _house_ptr_year_from_raw_path(raw_path)
    if year is None:
        fd = row.get("filing_date")
        if pd.notna(fd):
            y = int(pd.Timestamp(fd).year)
            if 1990 <= y <= 2100:
                year = y
    if year is None:
        return ""
    return HOUSE_PTR_PDF_URL.format(year=year, doc_id=doc_id)


def transaction_type_display_label(raw: object) -> str:
    s = "" if raw is None or (isinstance(raw, float) and pd.isna(raw)) else str(raw).strip()
    if not s or s.lower() == "unknown":
        return "Unknown"
    mapping = {
        "P": "Buy",
        "S": "Sell",
        "S (partial)": "Sell (partial)",
        "E": "Exchange",
    }
    return mapping.get(s, s)


def transaction_type_filter_option(raw: str) -> str:
    label = transaction_type_display_label(raw)
    r = str(raw).strip()
    if label == "Unknown" or label == r:
        return label
    return f"{label} ({r})"


def _signed_amount_median(row: pd.Series) -> float:
    low, high = row.get("amount_low"), row.get("amount_high")
    vals = [float(v) for v in (low, high) if pd.notna(v) and float(v) > 0]
    if not vals:
        ev = row.get("estimated_value")
        if pd.notna(ev) and float(ev) > 0:
            return float(ev)
        return 0.0
    return float(pd.Series(vals).median())


def _signed_trade_notional(row: pd.Series) -> float:
    med = _signed_amount_median(row)
    if med == 0:
        return 0.0
    tt = str(row.get("transaction_type", "")).strip()
    if tt == "P":
        return med
    if tt == "S" or tt.startswith("S"):
        return -med
    return 0.0


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
    data["transaction_type_label"] = data["transaction_type"].map(transaction_type_display_label)
    data["month"] = data["transaction_date"].dt.to_period("M").dt.to_timestamp()
    data["doc_id"] = data["doc_id"].map(lambda x: "" if pd.isna(x) else str(x).strip())
    data["source_url"] = data["source_url"].map(lambda x: "" if pd.isna(x) else str(x).strip())
    data["raw_document_path"] = data["raw_document_path"].map(lambda x: "" if pd.isna(x) else str(x).strip())
    data["disclosure_url"] = data.apply(_compute_disclosure_url_row, axis=1)
    return data[TRANSACTION_COLUMNS + ["estimated_value", "month", "disclosure_url", "transaction_type_label"]]


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
    data["transaction_type"] = data["transaction_type"].fillna("unknown")
    data["transaction_type_label"] = data["transaction_type"].map(transaction_type_display_label)
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


def _streamlit_theme_is_dark() -> bool:
    try:
        return getattr(st.context.theme, "type", None) == "dark"
    except Exception:
        return False


def _buy_sell_cell_style(value: object, *, dark: bool) -> str:
    """Muted buy/sell chips aligned with THEME (teal / accent / navy / gold), light vs dark Streamlit."""
    label = "" if value is None or (isinstance(value, float) and pd.isna(value)) else str(value).strip()
    t = THEME
    # Shared: left accent bar + light padding; no neon fills.
    def _cell(light_bg: str, light_ink: str, dark_bg: str, dark_ink: str, border: str) -> str:
        if dark:
            return (
                f"border-left: 3px solid {border}; background-color: {dark_bg}; color: {dark_ink}; "
                "font-weight: 600; padding: 0.2rem 0.5rem 0.2rem 0.45rem;"
            )
        return (
            f"border-left: 3px solid {border}; background-color: {light_bg}; color: {light_ink}; "
            "font-weight: 600; padding: 0.2rem 0.5rem 0.2rem 0.45rem;"
        )

    if label == "Buy":
        return _cell(
            "rgba(45, 111, 109, 0.12)",
            "#153d3b",
            "rgba(45, 111, 109, 0.26)",
            "#e4f2f0",
            t["teal"],
        )
    if label == "Sell":
        return _cell(
            t["accent_soft"],
            t["accent_deep"],
            "rgba(166, 75, 42, 0.26)",
            "#f8ece8",
            t["accent"],
        )
    if label == "Sell (partial)":
        return _cell(
            "rgba(198, 146, 43, 0.14)",
            "#5a4518",
            "rgba(198, 146, 43, 0.22)",
            "#f7efd8",
            t["gold"],
        )
    if label == "Exchange":
        return _cell(
            "rgba(32, 52, 74, 0.09)",
            t["navy"],
            "rgba(32, 52, 74, 0.32)",
            "#e8edf4",
            "#2d4a6e",
        )
    return _cell(
        "rgba(95, 103, 115, 0.10)",
        t["ink_soft"],
        "rgba(95, 103, 115, 0.22)",
        "#d8dce3",
        t["muted"],
    )


def _style_dataframe_buy_sell(frame: pd.DataFrame) -> pd.DataFrame | pd.io.formats.style.Styler:
    if frame.empty or "transaction_type_label" not in frame.columns:
        return frame
    dark = _streamlit_theme_is_dark()
    return frame.style.map(
        lambda v, d=dark: _buy_sell_cell_style(v, dark=d),
        subset=["transaction_type_label"],
    ).hide(axis="index")


def _altair_readability(chart: alt.Chart) -> alt.Chart:
    """Shared chart typography and high-contrast axes/legends (site-wide Altair defaults)."""
    return (
        chart.configure_axis(
            labelFontSize=13,
            titleFontSize=14,
            titleFontWeight="bold",
            labelFontWeight=500,
            labelColor=THEME["chart_axis_label"],
            titleColor=THEME["chart_axis_title"],
            domainColor=THEME["chart_axis_title"],
            tickColor=THEME["chart_axis_label"],
            labelPadding=5,
            titlePadding=10,
        )
        .configure_legend(
            labelFontSize=13,
            titleFontSize=14,
            titleFontWeight="bold",
            labelFontWeight=500,
            labelColor=THEME["chart_legend_label"],
            titleColor=THEME["chart_legend_title"],
            strokeColor="rgba(12, 16, 24, 0.14)",
            fillColor="rgba(255, 252, 246, 0.98)",
            padding=12,
            cornerRadius=6,
        )
        .configure_view(
            fill=THEME["chart_view_fill"],
            stroke=THEME["chart_view_stroke"],
            strokeWidth=1,
        )
        .configure_header(labelFontSize=13, titleFontSize=14, titleFontWeight="bold")
    )


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
            --caption-ink: __CAPTION_INK__;
            --body-secondary-strong: __BODY_SECONDARY_STRONG__;
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
        /* Main column: Streamlit captions default to low-contrast grey — force readable body text */
        [data-testid="stMain"] [data-testid="stCaptionContainer"] p,
        [data-testid="stMain"] [data-testid="stCaptionContainer"] div,
        [data-testid="stMain"] [data-testid="stCaptionContainer"] span,
        [data-testid="stMain"] [data-testid="stCaptionContainer"] label {
            color: var(--caption-ink) !important;
            opacity: 1 !important;
            font-size: 0.94rem !important;
            line-height: 1.58 !important;
            font-weight: 500 !important;
        }
        [data-testid="stMain"] h1,
        [data-testid="stMain"] h2,
        [data-testid="stMain"] h3 {
            color: var(--ink) !important;
        }
        [data-testid="stMain"] [data-testid="stMarkdownContainer"] p,
        [data-testid="stMain"] [data-testid="stMarkdownContainer"] li {
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
            min-height: 2.85rem !important;
            max-height: 10rem !important;
            overflow-y: auto !important;
            overflow-x: hidden !important;
            align-items: center !important;
            padding-top: 0.35rem !important;
            padding-bottom: 0.35rem !important;
        }
        [data-testid="stSidebar"] .stMultiSelect [data-baseweb="select"] [data-baseweb="value"] {
            line-height: 1.35 !important;
            min-height: 1.35em !important;
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
        .stButton > button:focus:not(:focus-visible),
        .stDownloadButton > button:focus:not(:focus-visible),
        button[kind="secondary"]:focus:not(:focus-visible) {
            box-shadow: 0 12px 24px rgba(126, 53, 29, 0.16);
        }
        .stButton > button:focus-visible,
        .stDownloadButton > button:focus-visible,
        button[kind="secondary"]:focus-visible {
            box-shadow: 0 0 0 3px rgba(166, 75, 42, 0.22), 0 12px 24px rgba(126, 53, 29, 0.16) !important;
            outline: none;
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
            color: var(--body-secondary-strong);
            font-size: 1rem;
            line-height: 1.7;
            max-width: 48rem;
            margin: 0.8rem 0 0 0;
            font-weight: 450;
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
            color: #3d4656;
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
            color: var(--body-secondary-strong);
            font-size: 0.92rem;
            line-height: 1.45;
            font-weight: 450;
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
            color: var(--body-secondary-strong);
            font-size: 0.94rem;
            font-weight: 450;
            line-height: 1.55;
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
            gap: 0.45rem;
            margin-bottom: 0.65rem;
            padding: 0.2rem 0;
            flex-wrap: wrap;
        }
        .stTabs [data-baseweb="tab"] {
            background: rgba(255, 250, 241, 0.72);
            border: 1px solid rgba(48, 58, 71, 0.10);
            border-radius: 999px;
            padding: 0.38rem 1.05rem;
            height: auto;
            min-height: 2.35rem;
            color: var(--ink);
            transition: background 0.15s ease, border-color 0.15s ease, color 0.15s ease;
        }
        .stTabs [data-baseweb="tab"] * {
            color: var(--ink);
        }
        .stTabs [data-baseweb="tab"]:hover {
            border-color: rgba(166, 75, 42, 0.28);
            background: rgba(255, 250, 241, 0.95);
        }
        .stTabs [data-baseweb="tab"]:focus-visible {
            outline: 2px solid var(--accent);
            outline-offset: 2px;
        }
        .stTabs [aria-selected="true"] {
            background: rgba(166, 75, 42, 0.14);
            color: var(--accent-deep);
            border-color: rgba(166, 75, 42, 0.35);
            font-weight: 700;
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
        /* Large / ultrawide: cap line length, add breathing room, keep charts readable */
        @media (min-width: 1280px) {
            section.main div.block-container {
                padding-left: clamp(1.25rem, 2.2vw, 3.5rem) !important;
                padding-right: clamp(1.25rem, 2.2vw, 3.5rem) !important;
            }
        }
        @media (min-width: 1440px) {
            section.main div.block-container {
                max-width: min(calc(100vw - 17.5rem), 1680px) !important;
                margin-left: auto !important;
                margin-right: auto !important;
            }
            .dashboard-shell {
                padding: 1.95rem 2rem 1.65rem 2rem;
            }
            .hero-title {
                font-size: 3rem;
            }
            .section-title {
                font-size: 1.28rem;
            }
            .metric-value {
                font-size: 2.1rem;
            }
        }
        @media (min-width: 1800px) {
            section.main div.block-container {
                max-width: min(calc(100vw - 18.5rem), 1980px) !important;
            }
            .dashboard-shell {
                padding: 2.1rem 2.25rem 1.75rem 2.25rem;
            }
            .hero-title {
                font-size: 3.25rem;
            }
            .hero-copy {
                font-size: 1.05rem;
                max-width: 52rem;
            }
            .section-title {
                font-size: 1.38rem;
            }
            .section-copy {
                font-size: 1rem;
            }
            .metric-value {
                font-size: 2.2rem;
            }
            [data-testid="stSidebar"] {
                min-width: 19.5rem;
            }
        }
        @media (max-width: 980px) {
            .hero-grid {
                grid-template-columns: 1fr;
            }
            .hero-title {
                font-size: 2.2rem;
            }
        }
        @media (prefers-reduced-motion: reduce) {
            .stTabs [data-baseweb="tab"],
            .stButton > button,
            .stDownloadButton > button,
            button[kind="secondary"] {
                transition: none;
            }
            .stButton > button:hover,
            .stDownloadButton > button:hover,
            button[kind="secondary"]:hover {
                transform: none;
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
        .replace("__CAPTION_INK__", THEME["ui_caption"])
        .replace("__BODY_SECONDARY_STRONG__", THEME["ui_body_secondary"])
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

    base = (
        alt.Chart(chart_data)
        .mark_area(line={"color": THEME["accent"], "strokeWidth": 3}, color="#d7a869", opacity=0.35)
        .encode(
            x=alt.X(
                "month:T",
                axis=alt.Axis(
                    title="Calendar month",
                    labelColor=THEME["chart_axis_label"],
                    titleColor=THEME["chart_axis_title"],
                    grid=True,
                    gridColor=THEME["chart_grid_major"],
                    format="%b %Y",
                ),
            ),
            y=alt.Y(
                "transactions:Q",
                axis=alt.Axis(
                    title="Disclosure rows in month",
                    labelColor=THEME["chart_axis_label"],
                    titleColor=THEME["chart_axis_title"],
                    tickCount=5,
                    gridColor=THEME["chart_grid_major"],
                ),
            ),
            tooltip=[
                alt.Tooltip("month_label:N", title="Month"),
                alt.Tooltip("transactions:Q", title="Transactions", format=",.0f"),
                alt.Tooltip("estimated_value:Q", title="Estimated Midpoint", format="$,.0f"),
            ],
        )
        .properties(height=300)
        .configure(background="transparent")
    )
    return _altair_readability(base)


def _build_rank_chart(
    frame: pd.DataFrame,
    label_field: str,
    title: str,
    *,
    color: str,
    y_axis_title: str | None = None,
) -> alt.Chart:
    chart_data = frame.copy()
    chart_data = chart_data.sort_values("transactions", ascending=False)
    y_title = y_axis_title or label_field.replace("_", " ").title()

    base = (
        alt.Chart(chart_data)
        .mark_bar(cornerRadiusTopRight=6, cornerRadiusBottomRight=6, color=color)
        .encode(
            x=alt.X(
                "transactions:Q",
                axis=alt.Axis(
                    title=title,
                    labelColor=THEME["chart_axis_label"],
                    titleColor=THEME["chart_axis_title"],
                    tickCount=5,
                    gridColor=THEME["chart_grid_major"],
                ),
            ),
            y=alt.Y(
                f"{label_field}:N",
                sort="-x",
                axis=alt.Axis(
                    title=y_title,
                    labelColor=THEME["chart_axis_label"],
                    titleColor=THEME["chart_axis_title"],
                    labelLimit=220,
                ),
            ),
            tooltip=[
                alt.Tooltip(f"{label_field}:N", title=title.rstrip("s")),
                alt.Tooltip("transactions:Q", title="Transactions", format=",.0f"),
                alt.Tooltip("estimated_value:Q", title="Estimated Midpoint", format="$,.0f"),
            ],
        )
        .properties(height=320)
        .configure(background="transparent")
    )
    return _altair_readability(base)


def _build_mix_chart(
    frame: pd.DataFrame,
    label_field: str,
    *,
    color: str,
    x_axis_title: str | None = None,
) -> alt.Chart:
    chart_data = frame.copy()
    x_title = x_axis_title or label_field.replace("_", " ").title()
    base = (
        alt.Chart(chart_data)
        .mark_bar(cornerRadiusTopLeft=8, cornerRadiusTopRight=8, color=color)
        .encode(
            x=alt.X(
                f"{label_field}:N",
                axis=alt.Axis(
                    title=x_title,
                    labelColor=THEME["chart_axis_label"],
                    titleColor=THEME["chart_axis_title"],
                    labelAngle=-25,
                    labelLimit=180,
                ),
            ),
            y=alt.Y(
                "transactions:Q",
                axis=alt.Axis(
                    title="Row count",
                    labelColor=THEME["chart_axis_label"],
                    titleColor=THEME["chart_axis_title"],
                    tickCount=4,
                    grid=True,
                    gridColor=THEME["chart_grid_major"],
                ),
            ),
            tooltip=[
                alt.Tooltip(f"{label_field}:N", title=label_field.replace("_", " ").title()),
                alt.Tooltip("transactions:Q", title="Transactions", format=",.0f"),
            ],
        )
        .properties(height=250)
        .configure(background="transparent")
    )
    return _altair_readability(base)


# Semantic colors for the member × time scatter (explicit domain avoids Altair assigning
# theme colors alphabetically, which obscures buy vs sell).
_TICKER_TIMELINE_TYPE_COLORS: dict[str, str] = {
    "Buy": "#15803d",
    "Sell": "#be123c",
    "Sell (partial)": "#c2410c",
    "Exchange": "#1d4ed8",
    "Unknown": "#64748b",
}


def _ticker_timeline_vertical_rule_dates(series: pd.Series) -> pd.DatetimeIndex:
    """Month-start rules for readability; weekly when the filtered window is short."""
    t0 = pd.Timestamp(series.min()).normalize()
    t1 = pd.Timestamp(series.max())
    span_days = max(1, int((t1 - t0).days) + 1)
    if span_days <= 100:
        return pd.date_range(t0 - pd.Timedelta(days=t0.weekday()), t1 + pd.Timedelta(days=1), freq="W-MON")
    if span_days <= 800:
        start = t0.to_period("M").to_timestamp()
        return pd.date_range(start, t1 + pd.Timedelta(days=1), freq="MS")
    start = t0.to_period("Q").to_timestamp()
    return pd.date_range(start, t1 + pd.Timedelta(days=1), freq="QS")


def _ticker_timeline_x_axis_format(span_days: int) -> tuple[str, int]:
    if span_days <= 45:
        return ("%d %b %y", min(18, max(6, span_days // 2)))
    if span_days <= 550:
        return ("%b '%y", 14)
    return ("%Y", max(4, min(12, span_days // 200)))


def _ticker_timeline_color_key_html(labels_in_use: list[str]) -> str:
    parts = []
    for lab in labels_in_use:
        c = _TICKER_TIMELINE_TYPE_COLORS.get(lab, "#64748b")
        parts.append(
            f'<span style="display:inline-flex;align-items:center;gap:0.35rem;margin-right:1rem;">'
            f'<span style="width:0.65rem;height:0.65rem;border-radius:999px;background:{c};'
            f'border:1px solid rgba(0,0,0,0.12);"></span>{lab}</span>'
        )
    inner = "".join(parts)
    return (
        f'<p style="margin:0.35rem 0 0.75rem 0;font-size:0.95rem;font-weight:500;color:{THEME["ui_caption"]};">'
        f"<strong>{_copy('ticker_color_key_title')}</strong> · {inner}</p>"
    )


def _build_ticker_member_timeline(frame: pd.DataFrame, ticker: str) -> alt.Chart | None:
    if not ticker or not str(ticker).strip():
        return None
    t = str(ticker).strip().upper()
    sub = frame[frame["ticker"].astype(str).str.upper() == t].copy()
    sub = sub.dropna(subset=["transaction_date"])
    if sub.empty:
        return None
    sub["txn_type_label"] = sub["transaction_type"].map(transaction_type_display_label)
    preferred = ["Buy", "Sell", "Sell (partial)", "Exchange", "Unknown"]
    present = sub["txn_type_label"].drop_duplicates().tolist()
    color_domain = [x for x in preferred if x in present] + sorted(x for x in present if x not in preferred)
    color_range = [_TICKER_TIMELINE_TYPE_COLORS.get(x, "#64748b") for x in color_domain]
    member_order = (
        sub.groupby("member", observed=True)["transaction_date"]
        .max()
        .sort_values(ascending=False)
        .index.tolist()
    )
    height = min(520, max(220, 32 * max(6, len(member_order))))
    span_days = max(1, int((sub["transaction_date"].max() - sub["transaction_date"].min()).days) + 1)
    date_fmt, tick_n = _ticker_timeline_x_axis_format(span_days)
    grid_axis = THEME["chart_grid_major"]
    x_axis = alt.Axis(
        title="Transaction date",
        format=date_fmt,
        tickCount=tick_n,
        labelAngle=-28,
        labelOverlap=False,
        labelColor=THEME["chart_axis_label"],
        titleColor=THEME["chart_axis_title"],
        grid=True,
        gridColor=grid_axis,
        gridDash=[2, 3],
        domainColor=THEME["chart_axis_title"],
        tickColor=THEME["chart_axis_label"],
        domainWidth=1,
    )
    y_axis = alt.Axis(
        title="Member",
        labelColor=THEME["chart_axis_label"],
        titleColor=THEME["chart_axis_title"],
        labelFontSize=12,
        labelLimit=240,
        grid=True,
        gridColor="rgba(18, 24, 34, 0.12)",
        domainColor=THEME["chart_axis_title"],
        tickColor=THEME["chart_axis_label"],
    )
    rules_df = pd.DataFrame({"transaction_date": _ticker_timeline_vertical_rule_dates(sub["transaction_date"])})
    vlines = (
        alt.Chart(rules_df)
        .mark_rule(
            color="rgba(32, 52, 74, 0.38)",
            strokeWidth=1,
            strokeDash=[5, 4],
        )
        .encode(x=alt.X("transaction_date:T", axis=None))
    )
    points = (
        alt.Chart(sub)
        .mark_circle(size=96, opacity=0.92, stroke="#ffffff", strokeWidth=1)
        .encode(
            x=alt.X("transaction_date:T", axis=x_axis),
            y=alt.Y("member:N", sort=member_order, axis=y_axis),
            color=alt.Color(
                "txn_type_label:N",
                title="Transaction type",
                scale=alt.Scale(domain=color_domain, range=color_range),
                legend=alt.Legend(
                    orient="bottom",
                    direction="horizontal",
                    titleFontWeight="bold",
                    labelColor=THEME["chart_legend_label"],
                    titleColor=THEME["chart_legend_title"],
                    labelLimit=220,
                    labelFontSize=13,
                    titleFontSize=14,
                    padding=12,
                    symbolType="circle",
                    symbolSize=130,
                ),
            ),
            tooltip=[
                alt.Tooltip("member:N", title="Member"),
                alt.Tooltip("transaction_date:T", title="Date", format="%Y-%m-%d"),
                alt.Tooltip("txn_type_label:N", title="Type"),
                alt.Tooltip("transaction_type:N", title="Raw code"),
                alt.Tooltip("amount_range_raw:N", title="Amount range"),
                alt.Tooltip("issuer_name:N", title="Issuer"),
                alt.Tooltip("chamber:N", title="Chamber"),
            ],
        )
    )
    base = (
        (vlines + points)
        .properties(height=height)
        .configure(background="transparent")
    )
    return _altair_readability(base)


def _build_ticker_3d_figure(frame: pd.DataFrame, ticker: str):
    """Plotly 3D scatter: date × member × log amount. Returns None if plotly missing or no rows."""
    try:
        import plotly.graph_objects as go
    except ImportError:
        return None
    if not ticker or not str(ticker).strip():
        return None
    t = str(ticker).strip().upper()
    sub = frame[frame["ticker"].astype(str).str.upper() == t].copy()
    sub = sub.dropna(subset=["transaction_date"])
    if sub.empty:
        return None
    sub = sub.copy()
    sub["txn_type_label"] = sub["transaction_type"].map(transaction_type_display_label)
    ev = pd.to_numeric(sub["estimated_value"], errors="coerce").fillna(0.0)
    sub["_z"] = np.log10(ev.clip(lower=0.0) + 1.0)
    member_order = (
        sub.groupby("member", observed=True)["transaction_date"]
        .max()
        .sort_values(ascending=False)
        .index.tolist()
    )
    sub["member"] = pd.Categorical(sub["member"], categories=member_order, ordered=True)
    sub = sub.sort_values(["transaction_date", "member"])
    color_map = {k: v for k, v in _TICKER_TIMELINE_TYPE_COLORS.items() if k in sub["txn_type_label"].unique()}
    traces = []
    for lab, g in sub.groupby("txn_type_label", observed=True):
        c = color_map.get(lab, _TICKER_TIMELINE_TYPE_COLORS.get(lab, "#64748b"))
        traces.append(
            go.Scatter3d(
                x=g["transaction_date"],
                y=g["member"].astype(str),
                z=g["_z"],
                mode="markers",
                name=lab,
                marker=dict(size=8, color=c, line=dict(width=0.5, color="rgba(255,255,255,0.9)")),
                hovertemplate=(
                    "<b>%{y}</b><br>"
                    "%{x|%Y-%m-%d}<br>"
                    "z = log₁₀(mid+1): %{z:.2f}<br>"
                    "<extra></extra>"
                ),
            )
        )
    ink = THEME["plotly_axis_ink"]
    tick = THEME["plotly_tick_ink"]
    leg = THEME["plotly_legend_ink"]
    bg = THEME["plotly_scene_bg"]
    grid_muted = "rgba(24, 32, 44, 0.38)"
    axis_title = dict(color=ink, size=14)
    tick_font = dict(color=tick, size=12)
    fig = go.Figure(data=traces)
    fig.update_layout(
        height=min(920, max(560, 30 * max(8, len(member_order)))),
        margin=dict(l=8, r=8, t=20, b=100),
        paper_bgcolor=THEME["plotly_paper"],
        font=dict(color=leg, size=13),
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.14,
            xanchor="center",
            x=0.5,
            bgcolor="rgba(255, 252, 246, 0.96)",
            bordercolor="rgba(18, 24, 34, 0.18)",
            borderwidth=1,
            title=dict(text="Transaction type", font=dict(color=leg, size=14)),
            font=dict(color=leg, size=13),
        ),
        scene=dict(
            xaxis=dict(
                title=dict(text="Date", font=axis_title),
                backgroundcolor=bg,
                gridcolor=grid_muted,
                showbackground=True,
                showspikes=True,
                spikecolor="rgba(166,75,42,0.55)",
                tickfont=tick_font,
            ),
            yaxis=dict(
                title=dict(text="Member", font=axis_title),
                backgroundcolor=bg,
                gridcolor=grid_muted,
                showbackground=True,
                tickfont=dict(color=tick, size=11),
                categoryorder="array",
                categoryarray=[str(m) for m in member_order],
            ),
            zaxis=dict(
                title=dict(text="log₁₀(est. midpoint + 1)", font=axis_title),
                backgroundcolor=bg,
                gridcolor=grid_muted,
                showbackground=True,
                tickfont=tick_font,
            ),
            aspectmode="manual",
            aspectratio=dict(x=2.0, y=1.35, z=0.85),
        ),
    )
    return fig


def _build_member_cumulative_notional_chart(
    frame: pd.DataFrame, ticker: str, *, top_n: int = 16
) -> tuple[alt.Chart | None, list[str]]:
    if not ticker or not str(ticker).strip():
        return None, []
    t = str(ticker).strip().upper()
    sub = frame[frame["ticker"].astype(str).str.upper().eq(t)].copy()
    sub = sub.dropna(subset=["transaction_date"])
    if sub.empty:
        return None, []

    sub["_signed"] = sub.apply(_signed_trade_notional, axis=1)
    member_counts = sub["member"].value_counts()
    keep_members = member_counts.head(top_n).index.tolist()
    sub = sub[sub["member"].isin(keep_members)]
    if sub.empty:
        return None, []

    sub = sub.sort_values(["member", "transaction_date", "filing_date"], ascending=[True, True, True])
    sub["cumulative_usd"] = sub.groupby("member", observed=True)["_signed"].cumsum()
    sub["trade_date_label"] = sub["transaction_date"].dt.strftime("%Y-%m-%d")
    sub["txn_type_label"] = sub["transaction_type"].map(transaction_type_display_label)

    member_order = sorted(sub["member"].dropna().astype(str).unique().tolist())
    n_members = len(member_order)
    height = min(480, max(240, 36 * max(4, min(n_members, 8))))

    chart = (
        alt.Chart(sub)
        .mark_line(point=True, strokeWidth=2.2, interpolate="monotone")
        .encode(
            x=alt.X(
                "transaction_date:T",
                title="Transaction date",
                axis=alt.Axis(
                    labelColor=THEME["chart_axis_label"],
                    titleColor=THEME["chart_axis_title"],
                    gridColor=THEME["chart_grid_major"],
                ),
            ),
            y=alt.Y(
                "cumulative_usd:Q",
                title="Cumulative signed median ($)",
                axis=alt.Axis(
                    labelColor=THEME["chart_axis_label"],
                    titleColor=THEME["chart_axis_title"],
                    tickCount=5,
                    gridColor=THEME["chart_grid_major"],
                    format="~s",
                ),
            ),
            color=alt.Color(
                "member:N",
                title="Member",
                scale=alt.Scale(domain=member_order),
                legend=alt.Legend(
                    orient="bottom",
                    direction="horizontal",
                    columns=min(3, max(1, n_members)),
                    title="Member (line color)",
                    labelFontSize=13,
                    titleFontSize=14,
                    titleFontWeight="bold",
                    labelFontWeight=500,
                    labelColor=THEME["chart_legend_label"],
                    titleColor=THEME["chart_legend_title"],
                    symbolSize=80,
                    symbolStrokeWidth=2,
                    columnPadding=14,
                    rowPadding=8,
                    padding=12,
                ),
            ),
            tooltip=[
                alt.Tooltip("member:N", title="Member"),
                alt.Tooltip("trade_date_label:N", title="Date"),
                alt.Tooltip("txn_type_label:N", title="Type"),
                alt.Tooltip("_signed:Q", title="Signed Δ ($)", format=",.0f"),
                alt.Tooltip("cumulative_usd:Q", title="Cumulative ($)", format=",.0f"),
                alt.Tooltip("amount_range_raw:N", title="Amount range"),
            ],
        )
        .properties(height=height)
        .configure(
            background="transparent",
            padding={"bottom": 110},
            view={
                "fill": THEME["chart_view_fill"],
                "stroke": THEME["chart_view_stroke"],
                "strokeWidth": 1,
            },
            legend={
                "labelColor": THEME["chart_legend_label"],
                "titleColor": THEME["chart_legend_title"],
                "labelFontSize": 13,
                "titleFontSize": 14,
                "strokeColor": "rgba(12, 16, 24, 0.12)",
                "fillColor": "rgba(255, 252, 246, 0.98)",
            },
        )
    )
    return chart, member_order


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


def _sidebar_typeahead_select(
    *,
    title: str,
    hint: str,
    options: list[str],
    widget_key: str,
    first: bool,
    placeholder: str,
) -> str | None:
    """Single Streamlit combobox: st.selectbox with index=None + accept_new_options (see docs for st.selectbox)."""
    _sidebar_filter_label(title, hint, first=first)
    return st.sidebar.selectbox(
        title,
        options,
        index=None,
        placeholder=placeholder,
        accept_new_options=True,
        label_visibility="collapsed",
        key=widget_key,
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
    """Scope first (dates, chamber), then typeahead selects (member, ticker, issuer), facets, confidence."""
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
        member_choice = _sidebar_typeahead_select(
            title=_copy("sidebar_pick_member_label"),
            hint=_copy("sidebar_member_filter_hint"),
            options=members_sorted,
            widget_key="sidebar_filter_member",
            first=first_label,
            placeholder=_copy("sidebar_member_filter_placeholder"),
        )
        first_label = False
        if member_choice:
            pat = re.escape(str(member_choice))
            mcol = filtered["member"].astype(str).str.strip()
            filtered = filtered[mcol.str.contains(pat, case=False, na=False, regex=True)]

    tickers_nonempty = sorted(
        {str(t).strip() for t in filtered["ticker"].dropna().unique() if str(t).strip()}
    )
    has_blank_ticker = filtered["ticker"].fillna("").astype(str).str.strip().eq("").any()
    if tickers_nonempty or has_blank_ticker:
        ticker_options: list[str] = []
        if has_blank_ticker:
            ticker_options.append(_SIDEBAR_NO_TICKER)
        ticker_options.extend(tickers_nonempty)
        ticker_choice = _sidebar_typeahead_select(
            title=_copy("sidebar_pick_ticker_label"),
            hint=_copy("sidebar_ticker_filter_hint"),
            options=ticker_options,
            widget_key="sidebar_filter_ticker",
            first=first_label,
            placeholder=_copy("sidebar_ticker_filter_placeholder"),
        )
        first_label = False
        if ticker_choice in (None, ""):
            pass
        elif ticker_choice in (_SIDEBAR_NO_TICKER, "-"):
            filtered = filtered[filtered["ticker"].fillna("").astype(str).str.strip().eq("")]
        else:
            tcol = filtered["ticker"].fillna("").astype(str).str.strip()
            pat = re.escape(str(ticker_choice))
            filtered = filtered[tcol.str.contains(pat, case=False, na=False, regex=True)]

    issuers_nonempty = sorted(
        {str(i).strip() for i in filtered["issuer_name"].dropna().unique() if str(i).strip()}
    )
    has_blank_issuer = filtered["issuer_name"].fillna("").astype(str).str.strip().eq("").any()
    if issuers_nonempty or has_blank_issuer:
        issuer_options: list[str] = []
        if has_blank_issuer:
            issuer_options.append(_SIDEBAR_NO_ISSUER)
        issuer_options.extend(issuers_nonempty)
        issuer_choice = _sidebar_typeahead_select(
            title=_copy("sidebar_pick_issuer_label"),
            hint=_copy("sidebar_issuer_filter_hint"),
            options=issuer_options,
            widget_key="sidebar_filter_issuer",
            first=first_label,
            placeholder=_copy("sidebar_issuer_filter_placeholder"),
        )
        first_label = False
        icol = filtered["issuer_name"].fillna("").astype(str).str.strip()
        if issuer_choice in (None, ""):
            pass
        elif issuer_choice in (_SIDEBAR_NO_ISSUER, "-"):
            filtered = filtered[icol.eq("")]
        elif issuer_choice:
            pat = re.escape(str(issuer_choice))
            filtered = filtered[icol.str.contains(pat, case=False, na=False, regex=True)]

    transaction_types = sorted(value for value in filtered["transaction_type"].dropna().astype(str).unique() if value)
    if transaction_types:
        _sidebar_filter_label(
            "Transaction type",
            "P = Buy, S = Sell (chips show full words plus the filing code).",
        )
        type_options = [transaction_type_filter_option(r) for r in transaction_types]
        option_to_raw = dict(zip(type_options, transaction_types))
        default_opts = type_options
        selected_opts = st.sidebar.multiselect(
            "Transaction Type",
            type_options,
            default=default_opts,
            label_visibility="collapsed",
            key="sidebar_transaction_type_filter",
        )
        selected_raws = [option_to_raw[o] for o in selected_opts if o in option_to_raw]
        if selected_raws:
            filtered = filtered[filtered["transaction_type"].isin(selected_raws)]

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
        page_icon="🏛️",
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

    st.divider()
    overview_tab, review_tab, raw_tab = st.tabs([_copy("tab_overview"), _copy("tab_review"), _copy("tab_raw")])

    with overview_tab:
        # Context and aggregate charts first (progressive disclosure — summary before row-level detail).
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
            filtered.groupby("transaction_type_label", as_index=False)
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
                st.caption(_copy("chart_caption_monthly"))
                st.altair_chart(_build_time_series_chart(monthly_activity), width="stretch")

            st.subheader(_copy("sub_top_members"))
            if top_members.empty:
                st.info("No member activity for the current filter.")
            else:
                st.caption(_copy("chart_caption_rank_members"))
                st.altair_chart(
                    _build_rank_chart(
                        top_members,
                        "member",
                        "Transaction count",
                        color=THEME["navy"],
                        y_axis_title="Member",
                    ),
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
                st.caption(_copy("chart_caption_mix_chamber"))
                st.altair_chart(
                    _build_mix_chart(chamber_mix, "chamber", color=THEME["teal"], x_axis_title="Chamber"),
                    width="stretch",
                )

            st.subheader(_copy("sub_transaction_type_mix"))
            if transaction_mix.empty:
                st.info("No transaction-type distribution for the current filter.")
            else:
                st.caption(_copy("chart_caption_mix_txn_type"))
                st.altair_chart(
                    _build_mix_chart(
                        transaction_mix,
                        "transaction_type_label",
                        color=THEME["accent"],
                        x_axis_title="Transaction type (display label)",
                    ),
                    width="stretch",
                )

            st.subheader(_copy("sub_top_tickers"))
            if top_tickers.empty:
                st.info("No resolved tickers in the current filter.")
            else:
                st.caption(_copy("chart_caption_rank_tickers"))
                st.altair_chart(
                    _build_rank_chart(
                        top_tickers,
                        "ticker",
                        "Transaction count",
                        color=THEME["gold"],
                        y_axis_title="Ticker",
                    ),
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

        st.divider()
        st.subheader(_copy("overview_detail_heading"))
        st.caption(_copy("overview_detail_caption"))

        latest_transactions = filtered.sort_values(
            ["transaction_date", "filing_date"],
            ascending=[False, False],
        ).head(50)
        st.subheader(_copy("sub_latest_transactions"))
        _latest_df = latest_transactions[
            [
                "transaction_date",
                "filing_date",
                "filing_type",
                "member",
                "chamber",
                "issuer_name",
                "ticker",
                "transaction_type_label",
                "transaction_type",
                "amount_range_raw",
                "confidence_score",
                "review_status",
                "disclosure_url",
            ]
        ]
        st.dataframe(
            _style_dataframe_buy_sell(_latest_df),
            hide_index=True,
            width="stretch",
            height=420,
            column_config={
                "transaction_date": st.column_config.DateColumn("Transaction Date", format="YYYY-MM-DD"),
                "filing_date": st.column_config.DateColumn("Filing Date", format="YYYY-MM-DD"),
                "transaction_type_label": st.column_config.TextColumn(
                    "Buy / Sell",
                    help="P = purchase (Buy). S = sale (Sell). Partial sales count as sells.",
                ),
                "transaction_type": st.column_config.TextColumn(
                    "Code",
                    help="Raw code from the disclosure (P, S, S (partial), E, …).",
                ),
                "confidence_score": st.column_config.ProgressColumn(
                    "Confidence",
                    format="%.2f",
                    min_value=0.0,
                    max_value=1.0,
                ),
                "disclosure_url": st.column_config.LinkColumn(
                    "Source PDF (PTR)",
                    help=(
                        "U.S. House Periodic Transaction Report (PTR) on disclosures-clerk.house.gov when year and "
                        "DocID are known. Congressional PTRs are not SEC Form 13F institutional holdings filings."
                    ),
                    display_text="Open PDF",
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
                "clear the sidebar Member / Ticker text filters, or pick a different issuer; many disclosures still lack ticker mapping."
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
                slice_tick = filtered[filtered["ticker"].astype(str).str.upper().eq(ticker_for_chart)]
                labs = slice_tick["transaction_type"].map(transaction_type_display_label).astype(str).unique().tolist()
                preferred = ["Buy", "Sell", "Sell (partial)", "Exchange", "Unknown"]
                color_key_order = [x for x in preferred if x in labs] + sorted(x for x in labs if x not in preferred)
                st.markdown(_ticker_timeline_color_key_html(color_key_order), unsafe_allow_html=True)
                st.altair_chart(ticker_chart, width="stretch")
                st.subheader(_copy("sub_ticker_3d"))
                st.caption(_copy("ticker_3d_caption"))
                fig_3d = _build_ticker_3d_figure(filtered, ticker_for_chart)
                if fig_3d is None:
                    st.warning("Install **plotly** (`pip install plotly`) to use the 3D view.")
                else:
                    st.plotly_chart(fig_3d, width="stretch")

            st.subheader(_copy("sub_cumulative_exposure"))
            st.caption(_copy("cumulative_exposure_caption"))
            cum_chart, _cum_members = _build_member_cumulative_notional_chart(filtered, ticker_for_chart)
            if cum_chart is None:
                st.info(
                    f"No dated transactions for ticker **{ticker_for_chart}** in the current slice "
                    "— pick another ticker or widen filters."
                )
            else:
                st.caption(
                    "At most 16 members are drawn (those with the most trades on this ticker in the current slice)."
                )
                st.caption(_copy("chart_caption_cumulative"))
                st.altair_chart(cum_chart, width="stretch")

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
            with review_cols[0]:
                st.caption(_copy("chart_caption_mix_review_reason"))
                st.altair_chart(
                    _build_mix_chart(
                        review_reason_counts.rename(columns={"records": "transactions"}),
                        "reason",
                        color=THEME["navy"],
                        x_axis_title="Review reason",
                    ),
                    width="stretch",
                )
            with review_cols[1]:
                st.caption(_copy("chart_caption_mix_review_status"))
                st.altair_chart(
                    _build_mix_chart(
                        review_status_counts.rename(columns={"records": "transactions"}),
                        "status",
                        color=THEME["accent"],
                        x_axis_title="Review status",
                    ),
                    width="stretch",
                )
            _review_df = filtered_review.sort_values(["transaction_date", "filing_date"], ascending=[False, False])
            st.dataframe(
                _style_dataframe_buy_sell(_review_df),
                hide_index=True,
                width="stretch",
                height=520,
                column_config={
                    "transaction_date": st.column_config.DateColumn("Transaction Date", format="YYYY-MM-DD"),
                    "filing_date": st.column_config.DateColumn("Filing Date", format="YYYY-MM-DD"),
                    "transaction_type_label": st.column_config.TextColumn("Buy / Sell"),
                    "transaction_type": st.column_config.TextColumn("Code"),
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
        show_polygon_est = st.checkbox(
            "Show Polygon return estimates (SQLite cache only; no API calls from this page)",
            value=False,
            key="raw_polygon_estimates",
        )
        st.caption(
            "Populates `polygon_daily_bar_cache` via CLI: `python -m src.main warm-polygon-price-cache` "
            "or `python -m src.main export-csv --polygon-pnl --as-of YYYY-MM-DD`."
        )
        conn_poly = get_connection()
        try:
            init_db(conn_poly)
            polygon_cache_rows = _polygon_daily_bar_cache_size(conn_poly)
        finally:
            conn_poly.close()
        _raw_base = filtered.sort_values(["transaction_date", "filing_date"], ascending=[False, False])
        _raw_df = _raw_base
        if show_polygon_est:
            if polygon_cache_rows == 0:
                st.info(
                    "Polygon daily bar cache is empty. From the repo root run "
                    "`python -m src.main warm-polygon-price-cache` (requires `POLYGON_API_KEY`), then refresh this page."
                )
            else:
                _raw_df = merge_polygon_pnl_cached_columns(_raw_base, as_of=date.today())
        st.download_button(
            label="Download filtered transactions as CSV",
            data=_download_bytes(_raw_df),
            file_name="congress_transactions_filtered.csv",
            mime="text/csv",
        )
        st.dataframe(
            _style_dataframe_buy_sell(_raw_df),
            hide_index=True,
            width="stretch",
            height=620,
            column_config={
                "transaction_date": st.column_config.DateColumn("Transaction Date", format="YYYY-MM-DD"),
                "filing_date": st.column_config.DateColumn("Filing Date", format="YYYY-MM-DD"),
                "transaction_type_label": st.column_config.TextColumn(
                    "Buy / Sell",
                    help="P = Buy, S = Sell (and partial sell).",
                ),
                "transaction_type": st.column_config.TextColumn("Code"),
                "amount_low": st.column_config.NumberColumn("Amount Low", format="$%d"),
                "amount_high": st.column_config.NumberColumn("Amount High", format="$%d"),
                "estimated_value": st.column_config.NumberColumn("Median of range", format="$%d"),
                "confidence_score": st.column_config.ProgressColumn(
                    "Confidence",
                    format="%.2f",
                    min_value=0.0,
                    max_value=1.0,
                ),
            },
        )