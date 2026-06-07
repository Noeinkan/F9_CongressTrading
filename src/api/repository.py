"""Streamlit-free data access for the API layer.

Ports the pure data-loading + preparation logic that the Streamlit dashboard
keeps in ``src.dashboard_shared.data`` (which is unusable here because it is
decorated with ``st.cache_data``). Caching is replaced with a small
in-process memo keyed on the same source-file mtimes the dashboard used, so
repeated requests do not re-read SQLite.

When the Streamlit dashboard is deleted at cutover, this module becomes the
single source of truth for loading normalized transactions and the review
queue.
"""
from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path
from threading import Lock
from typing import Optional

import pandas as pd

from ..config import DB_PATH, HOUSE_PTR_PDF_URL
from ..db import get_connection, init_db
from ._constants import (
    NORMALIZED_EXPORT_PATH,
    REVIEW_COLUMNS,
    REVIEW_EXPORT_PATH,
    SQLITE_REVIEW_QUERY,
    SQLITE_TRANSACTION_QUERY,
    TRANSACTION_COLUMNS,
)

_QUARTER_OPTIONS: tuple[int, ...] = (1, 2, 3, 4)


# --------------------------------------------------------------------------- #
# Low-level helpers (ported from dashboard_shared.data)
# --------------------------------------------------------------------------- #
def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def polygon_daily_bar_cache_size(conn: sqlite3.Connection) -> int:
    if not _table_exists(conn, "polygon_daily_bar_cache"):
        return 0
    try:
        return int(conn.execute("SELECT COUNT(*) FROM polygon_daily_bar_cache").fetchone()[0])
    except sqlite3.Error:
        return 0


def _empty_frame(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=columns)


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
    """Best URL for the originating disclosure PDF (House PTR when inferable)."""
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


def _load_ticker_sector_fallback(conn: sqlite3.Connection) -> dict[str, tuple[str, str]]:
    """Best sector/industry per ticker from issuers then asset_resolution_cache."""
    fallback: dict[str, tuple[str, str]] = {}
    if _table_exists(conn, "issuers"):
        for row in conn.execute(
            """
            SELECT UPPER(ticker) AS ticker, sector, industry
            FROM issuers
            WHERE COALESCE(ticker, '') <> ''
            ORDER BY
                CASE WHEN sector <> '' THEN 0 ELSE 1 END,
                CASE WHEN industry <> '' THEN 0 ELSE 1 END
            """
        ).fetchall():
            t = str(row["ticker"]).strip().upper()
            if t and t not in fallback and (row["sector"] or row["industry"]):
                fallback[t] = (row["sector"] or "", row["industry"] or "")
    if _table_exists(conn, "asset_resolution_cache"):
        for row in conn.execute(
            """
            SELECT UPPER(ticker) AS ticker, sector, industry
            FROM asset_resolution_cache
            WHERE COALESCE(ticker, '') <> ''
            ORDER BY confidence_score DESC
            """
        ).fetchall():
            t = str(row["ticker"]).strip().upper()
            if not t:
                continue
            sector, industry = row["sector"] or "", row["industry"] or ""
            if t not in fallback and (sector or industry):
                fallback[t] = (sector, industry)
            elif t in fallback and not fallback[t][0] and sector:
                fallback[t] = (sector, fallback[t][1] or industry)
    return fallback


def _fill_missing_sector_industry(data: pd.DataFrame) -> pd.DataFrame:
    if data.empty or "ticker" not in data.columns:
        return data
    needs = data["sector"].fillna("").astype(str).str.strip().eq("") | data[
        "industry"
    ].fillna("").astype(str).str.strip().eq("")
    if not needs.any():
        return data
    conn = get_connection()
    try:
        init_db(conn)
        fallback = _load_ticker_sector_fallback(conn)
    finally:
        conn.close()
    if not fallback:
        return data
    out = data.copy()
    if "sector" not in out.columns:
        out["sector"] = ""
    if "industry" not in out.columns:
        out["industry"] = ""
    for idx, row in out.loc[needs].iterrows():
        ticker = str(row.get("ticker") or "").strip().upper()
        if not ticker or ticker not in fallback:
            continue
        sector, industry = fallback[ticker]
        if not str(out.at[idx, "sector"]).strip() and sector:
            out.at[idx, "sector"] = sector
        if not str(out.at[idx, "industry"]).strip() and industry:
            out.at[idx, "industry"] = industry
    return out


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
    data["ticker"] = data["ticker"].fillna("").astype(str).str.upper()
    data["member"] = data["member"].fillna("Unknown")
    data["party"] = data["party"].fillna("")
    data["state"] = data["state"].fillna("")
    data["issuer_name"] = data["issuer_name"].fillna("")
    data["sector"] = data["sector"].fillna("").astype(str).str.strip()
    data["industry"] = data["industry"].fillna("").astype(str).str.strip()
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
    data["raw_document_path"] = data["raw_document_path"].map(
        lambda x: "" if pd.isna(x) else str(x).strip()
    )
    data["disclosure_url"] = data.apply(_compute_disclosure_url_row, axis=1)
    data = _fill_missing_sector_industry(data)
    return data[TRANSACTION_COLUMNS + ["month", "disclosure_url", "transaction_type_label"]]


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


def _load_transactions_uncached() -> tuple[pd.DataFrame, str]:
    conn = get_connection()
    try:
        init_db(conn)
        if _table_exists(conn, "transactions"):
            count = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
            if count:
                frame = pd.read_sql_query(SQLITE_TRANSACTION_QUERY, conn)
                return _prepare_transactions(frame), f"sqlite:{DB_PATH.name}"
    finally:
        conn.close()

    if NORMALIZED_EXPORT_PATH.exists():
        return _prepare_transactions(pd.read_csv(NORMALIZED_EXPORT_PATH)), f"csv:{NORMALIZED_EXPORT_PATH.name}"

    return _prepare_transactions(_empty_frame(TRANSACTION_COLUMNS)), "empty"


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


# --------------------------------------------------------------------------- #
# In-process cache keyed on source-file mtimes (mirrors the dashboard cache key)
# --------------------------------------------------------------------------- #
def _data_cache_key() -> str:
    parts: list[str] = []
    if DB_PATH.exists():
        parts.append(f"db:{DB_PATH.stat().st_mtime_ns}")
    if NORMALIZED_EXPORT_PATH.exists():
        parts.append(f"csv:{NORMALIZED_EXPORT_PATH.stat().st_mtime_ns}")
    if REVIEW_EXPORT_PATH.exists():
        parts.append(f"review:{REVIEW_EXPORT_PATH.stat().st_mtime_ns}")
    return "|".join(parts) if parts else "empty"


_cache_lock = Lock()
_cache_key: Optional[str] = None
_cache_transactions: Optional[tuple[pd.DataFrame, str]] = None
_cache_review: Optional[tuple[pd.DataFrame, str]] = None


def load_transactions() -> tuple[pd.DataFrame, str]:
    """Return (transactions, source_label); memoized on source-file mtimes."""
    global _cache_key, _cache_transactions, _cache_review
    key = _data_cache_key()
    with _cache_lock:
        if key != _cache_key:
            _cache_key = key
            _cache_transactions = None
            _cache_review = None
        if _cache_transactions is None:
            _cache_transactions = _load_transactions_uncached()
        return _cache_transactions


def load_review_queue(transactions: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    """Return (review_queue, source_label); memoized alongside transactions."""
    global _cache_review
    with _cache_lock:
        if _cache_review is None:
            _cache_review = _load_review_queue_uncached(transactions)
        return _cache_review


def load_dataset() -> dict[str, object]:
    """Load transactions + review queue and return a context dict.

    Mirrors the shape the Streamlit pages consumed via ``get_dashboard_context``
    (minus the period slice, which callers apply with :func:`apply_period_filter`).
    """
    transactions, transaction_source = load_transactions()
    review, review_source = load_review_queue(transactions)
    return {
        "transactions": transactions,
        "review": review,
        "transaction_source": transaction_source,
        "review_source": review_source,
        "ready": not transactions.empty,
    }


# --------------------------------------------------------------------------- #
# Period filtering (ported from dashboard_shared.filters)
# --------------------------------------------------------------------------- #
def available_years(data: pd.DataFrame) -> list[int]:
    if "transaction_date" not in data.columns:
        return []
    dates = pd.to_datetime(data["transaction_date"], errors="coerce").dropna()
    if dates.empty:
        return []
    return sorted(int(y) for y in dates.dt.year.unique())


def lookback_years(years_available: list[int], n_years: int | None) -> list[int]:
    """Calendar years included for a given lookback window (None = all)."""
    if n_years is None:
        return years_available
    current_year = date.today().year
    cutoff_year = current_year - n_years + 1
    return [y for y in years_available if y >= cutoff_year]


def apply_period_filter(
    data: pd.DataFrame,
    *,
    selected_years: list[int] | None,
    selected_quarters: list[int] | None,
    all_years: list[int],
    all_quarters: tuple[int, ...] = _QUARTER_OPTIONS,
) -> pd.DataFrame:
    """Keep rows whose transaction_date falls in selected calendar years/quarters."""
    if data.empty or "transaction_date" not in data.columns:
        return data

    years_sel = list(selected_years or [])
    quarters_sel = list(selected_quarters or [])
    if not years_sel or not quarters_sel:
        return data.iloc[0:0].copy()

    if set(years_sel) >= set(all_years) and set(quarters_sel) >= set(all_quarters):
        return data

    dated = data.dropna(subset=["transaction_date"]).copy()
    if dated.empty:
        return dated

    tx_dates = pd.to_datetime(dated["transaction_date"], errors="coerce")
    mask = tx_dates.dt.year.isin(years_sel) & tx_dates.dt.quarter.isin(quarters_sel)
    return dated.loc[mask].copy()


def filter_by_lookback(
    data: pd.DataFrame,
    *,
    lookback: int | None,
    quarters: list[int] | None,
) -> pd.DataFrame:
    """Apply a lookback-window (years) + quarter filter, the way the sidebar did.

    ``lookback`` is the number of years to look back (None = all time).
    ``quarters`` defaults to all four quarters when not provided.
    """
    years_all = available_years(data)
    selected_years = lookback_years(years_all, lookback)
    selected_quarters = list(quarters) if quarters else list(_QUARTER_OPTIONS)
    return apply_period_filter(
        data,
        selected_years=selected_years,
        selected_quarters=selected_quarters,
        all_years=years_all,
    )


def filter_review_to_slice(
    review_queue: pd.DataFrame, filtered_transactions: pd.DataFrame
) -> pd.DataFrame:
    """Restrict the review queue to rows matching the filtered transaction slice.

    Ported from ``dashboard_shared.session._filter_review_queue``.
    """
    if review_queue.empty or filtered_transactions.empty:
        return review_queue.iloc[0:0].copy()

    def _key(frame: pd.DataFrame) -> pd.Series:
        return (
            frame["member"].astype(str)
            + "|"
            + frame["asset_name_raw"].astype(str)
            + "|"
            + frame["transaction_type"].astype(str)
            + "|"
            + frame["amount_range_raw"].astype(str)
            + "|"
            + frame["transaction_date"].astype(str)
        )

    review_keys = _key(review_queue)
    filtered_keys = set(_key(filtered_transactions))
    return review_queue[review_keys.isin(filtered_keys)].copy()
