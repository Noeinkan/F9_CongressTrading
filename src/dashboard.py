from __future__ import annotations

from io import BytesIO
from pathlib import Path
import sqlite3

import pandas as pd
import streamlit as st

from .config import DATA_DIR, DB_PATH
from .db import get_connection, init_db

NORMALIZED_EXPORT_PATH = DATA_DIR / "congress_trades.csv"
REVIEW_EXPORT_PATH = DATA_DIR / "review_queue.csv"

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
    st.markdown(
        """
        <style>
        .stApp {
            background:
                radial-gradient(circle at top left, rgba(160, 196, 255, 0.22), transparent 30%),
                radial-gradient(circle at top right, rgba(255, 214, 165, 0.20), transparent 28%),
                linear-gradient(180deg, #f7f4ec 0%, #f4efe6 42%, #efe6d8 100%);
        }
        div[data-testid="stMetric"] {
            background: rgba(255, 252, 246, 0.78);
            border: 1px solid rgba(107, 79, 47, 0.16);
            border-radius: 18px;
            padding: 0.9rem 1rem;
            box-shadow: 0 12px 30px rgba(92, 68, 40, 0.08);
        }
        .dashboard-shell {
            background: rgba(255, 251, 245, 0.78);
            border: 1px solid rgba(107, 79, 47, 0.14);
            border-radius: 24px;
            padding: 1.25rem 1.35rem;
            box-shadow: 0 16px 38px rgba(92, 68, 40, 0.08);
            margin-bottom: 1rem;
        }
        .eyebrow {
            color: #8a5a1d;
            font-size: 0.8rem;
            font-weight: 700;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }
        .hero-title {
            color: #23180e;
            font-size: 2.4rem;
            line-height: 1.05;
            font-weight: 700;
            margin: 0.3rem 0 0.6rem 0;
        }
        .hero-copy {
            color: #57412c;
            font-size: 1rem;
            max-width: 56rem;
            margin: 0;
        }
        .source-pill {
            display: inline-block;
            margin-top: 0.85rem;
            padding: 0.35rem 0.7rem;
            border-radius: 999px;
            background: #16324f;
            color: #f8fafc;
            font-size: 0.82rem;
            font-weight: 600;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _apply_filters(data: pd.DataFrame) -> pd.DataFrame:
    filtered = data.copy()
    st.sidebar.header("Filters")

    chambers = sorted(value for value in filtered["chamber"].dropna().astype(str).unique() if value)
    if chambers:
        selected_chambers = st.sidebar.multiselect("Chamber", chambers, default=chambers)
        filtered = filtered[filtered["chamber"].isin(selected_chambers)]

    transaction_types = sorted(value for value in filtered["transaction_type"].dropna().astype(str).unique() if value)
    if transaction_types:
        selected_types = st.sidebar.multiselect("Transaction Type", transaction_types, default=transaction_types)
        filtered = filtered[filtered["transaction_type"].isin(selected_types)]

    asset_types = sorted(value for value in filtered["asset_type"].dropna().astype(str).unique() if value)
    if asset_types:
        selected_asset_types = st.sidebar.multiselect("Asset Type", asset_types, default=asset_types)
        filtered = filtered[filtered["asset_type"].isin(selected_asset_types)]

    review_statuses = sorted(value for value in filtered["review_status"].dropna().astype(str).unique() if value)
    if review_statuses:
        selected_statuses = st.sidebar.multiselect("Review Status", review_statuses, default=review_statuses)
        filtered = filtered[filtered["review_status"].isin(selected_statuses)]

    valid_dates = filtered["transaction_date"].dropna()
    if not valid_dates.empty:
        min_date = valid_dates.min().date()
        max_date = valid_dates.max().date()
        date_range = st.sidebar.date_input("Transaction Date Range", value=(min_date, max_date), min_value=min_date, max_value=max_date)
        if isinstance(date_range, tuple) and len(date_range) == 2:
            start_date, end_date = date_range
            filtered = filtered[
                filtered["transaction_date"].between(pd.Timestamp(start_date), pd.Timestamp(end_date))
            ]

    search = st.sidebar.text_input("Search Member / Asset / Ticker")
    if search:
        mask = (
            filtered["member"].astype(str).str.contains(search, case=False, na=False)
            | filtered["asset_name_raw"].astype(str).str.contains(search, case=False, na=False)
            | filtered["asset_name_normalized"].astype(str).str.contains(search, case=False, na=False)
            | filtered["ticker"].astype(str).str.contains(search, case=False, na=False)
            | filtered["issuer_name"].astype(str).str.contains(search, case=False, na=False)
        )
        filtered = filtered[mask]

    confidence_threshold = st.sidebar.slider("Minimum Confidence", min_value=0.0, max_value=1.0, value=0.0, step=0.05)
    filtered = filtered[filtered["confidence_score"] >= confidence_threshold]
    return filtered


def _render_empty_state() -> None:
    st.warning("No normalized transactions found yet. Run ingestion or export first, then refresh the dashboard.")
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


def render_dashboard() -> None:
    st.set_page_config(
        page_title="Congress Trading Dashboard",
        page_icon="/",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _inject_styles()

    transactions, transaction_source = load_transactions()
    review_queue, review_source = load_review_queue(transactions)

    st.markdown(
        f"""
        <section class="dashboard-shell">
            <div class="eyebrow">Congress Trading</div>
            <h1 class="hero-title">Normalized activity dashboard</h1>
            <p class="hero-copy">
                First analyst surface on top of the normalized House and Senate tracker. Filter live transaction data,
                inspect top members and tickers, and monitor unresolved records that still need review.
            </p>
            <div class="source-pill">Transactions: {transaction_source} | Review: {review_source}</div>
        </section>
        """,
        unsafe_allow_html=True,
    )

    if transactions.empty:
        _render_empty_state()
        return

    filtered = _apply_filters(transactions)
    filtered_review = review_queue.copy()
    if not filtered_review.empty:
        filtered_review = filtered_review[
            filtered_review["member"].isin(filtered["member"].unique())
        ]

    total_transactions = len(filtered)
    total_members = filtered["member"].nunique()
    tracked_tickers = filtered.loc[filtered["ticker"] != "", "ticker"].nunique()
    open_reviews = int((filtered_review["status"] == "open").sum()) if not filtered_review.empty else 0
    estimated_value = filtered["estimated_value"].sum(skipna=True)
    avg_confidence = filtered["confidence_score"].mean() if total_transactions else 0.0

    metric_columns = st.columns(5)
    metric_columns[0].metric("Transactions", f"{total_transactions:,}")
    metric_columns[1].metric("Members", f"{total_members:,}")
    metric_columns[2].metric("Tickers", f"{tracked_tickers:,}")
    metric_columns[3].metric("Open Reviews", f"{open_reviews:,}")
    metric_columns[4].metric("Estimated Midpoint", _format_currency(estimated_value), f"avg confidence {avg_confidence:.0%}")

    overview_tab, review_tab, raw_tab = st.tabs(["Overview", "Review Queue", "Raw Data"])

    with overview_tab:
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
            st.subheader("Monthly activity")
            if monthly_activity.empty:
                st.info("No valid transaction dates in the current filter.")
            else:
                timeline = monthly_activity.set_index("month")[["transactions", "estimated_value"]]
                st.line_chart(timeline)

            st.subheader("Top members")
            if top_members.empty:
                st.info("No member activity for the current filter.")
            else:
                st.bar_chart(top_members.set_index("member")[["transactions"]])
                st.dataframe(
                    top_members,
                    hide_index=True,
                    use_container_width=True,
                    column_config={
                        "estimated_value": st.column_config.NumberColumn("Estimated Midpoint", format="$%d"),
                    },
                )

        with right:
            st.subheader("Chamber mix")
            if chamber_mix.empty:
                st.info("No chamber distribution for the current filter.")
            else:
                st.bar_chart(chamber_mix.set_index("chamber")[["transactions"]])

            st.subheader("Transaction type mix")
            if transaction_mix.empty:
                st.info("No transaction-type distribution for the current filter.")
            else:
                st.bar_chart(transaction_mix.set_index("transaction_type")[["transactions"]])

            st.subheader("Top tickers")
            if top_tickers.empty:
                st.info("No resolved tickers in the current filter.")
            else:
                st.bar_chart(top_tickers.set_index("ticker")[["transactions"]])
                st.dataframe(
                    top_tickers,
                    hide_index=True,
                    use_container_width=True,
                    column_config={
                        "estimated_value": st.column_config.NumberColumn("Estimated Midpoint", format="$%d"),
                    },
                )

        latest_transactions = filtered.sort_values(
            ["transaction_date", "filing_date"],
            ascending=[False, False],
        ).head(50)
        st.subheader("Latest transactions")
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
            use_container_width=True,
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

    with review_tab:
        st.subheader("Records needing review")
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
            review_cols[0].bar_chart(review_reason_counts.set_index("reason")[["records"]])
            review_cols[1].bar_chart(review_status_counts.set_index("status")[["records"]])
            st.dataframe(
                filtered_review.sort_values(["transaction_date", "filing_date"], ascending=[False, False]),
                hide_index=True,
                use_container_width=True,
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
        st.subheader("Filtered normalized dataset")
        st.download_button(
            label="Download filtered transactions as CSV",
            data=_download_bytes(filtered),
            file_name="congress_transactions_filtered.csv",
            mime="text/csv",
        )
        st.dataframe(
            filtered.sort_values(["transaction_date", "filing_date"], ascending=[False, False]),
            hide_index=True,
            use_container_width=True,
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