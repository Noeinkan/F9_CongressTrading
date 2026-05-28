from __future__ import annotations

from datetime import date
from io import BytesIO
from pathlib import Path
import sqlite3

import pandas as pd
import streamlit as st

from ..config import DB_PATH, HOUSE_PTR_PDF_URL
from ..db import get_connection, init_db

from .constants import (
    NORMALIZED_EXPORT_PATH,
    REVIEW_COLUMNS,
    REVIEW_EXPORT_PATH,
    SQLITE_REVIEW_QUERY,
    SQLITE_TRANSACTION_QUERY,
    TRANSACTION_COLUMNS,
)

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
    data["party"] = data["party"].fillna("")
    data["state"] = data["state"].fillna("")
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


def _data_cache_key() -> str:
    parts: list[str] = []
    if DB_PATH.exists():
        parts.append(f"db:{DB_PATH.stat().st_mtime_ns}")
    if NORMALIZED_EXPORT_PATH.exists():
        parts.append(f"csv:{NORMALIZED_EXPORT_PATH.stat().st_mtime_ns}")
    if REVIEW_EXPORT_PATH.exists():
        parts.append(f"review:{REVIEW_EXPORT_PATH.stat().st_mtime_ns}")
    return "|".join(parts) if parts else "empty"


@st.cache_data(show_spinner=False)
def load_transactions_cached(cache_key: str) -> tuple[pd.DataFrame, str]:
    del cache_key
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


def load_transactions() -> tuple[pd.DataFrame, str]:
    return load_transactions_cached(_data_cache_key())


@st.cache_data(show_spinner=False)
def _load_review_queue_cached(cache_key: str, transactions_json: str) -> tuple[pd.DataFrame, str]:
    del cache_key
    transactions = pd.read_json(transactions_json) if transactions_json else _empty_frame(TRANSACTION_COLUMNS)
    if not transactions.empty:
        transactions = _prepare_transactions(transactions)
    return _load_review_queue_uncached(transactions)


def _load_review_queue_uncached(transactions: pd.DataFrame) -> tuple[pd.DataFrame, str]:
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


def load_review_queue(transactions: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    if transactions.empty:
        return _load_review_queue_uncached(transactions)
    tx_json = transactions.to_json(orient="records", date_format="iso")
    return _load_review_queue_cached(_data_cache_key(), tx_json)


def _format_currency(value: float) -> str:
    if pd.isna(value) or value <= 0:
        return "n/a"
    return f"${value:,.0f}"


def _download_bytes(frame: pd.DataFrame) -> bytes:
    buffer = BytesIO()
    frame.to_csv(buffer, index=False)
    return buffer.getvalue()

def load_polygon_bars(ticker: str) -> pd.DataFrame:
    t = str(ticker).strip().upper()
    if not t:
        return pd.DataFrame()
    conn = get_connection()
    try:
        init_db(conn)
        if not _table_exists(conn, "polygon_daily_bar_cache"):
            return pd.DataFrame()
        return pd.read_sql_query(
            """
            SELECT bar_date AS date, close
            FROM polygon_daily_bar_cache
            WHERE ticker = ?
            ORDER BY bar_date
            """,
            conn,
            params=(t,),
        )
    finally:
        conn.close()
