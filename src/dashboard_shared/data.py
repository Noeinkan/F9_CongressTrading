from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from io import BytesIO
import json
from pathlib import Path
import sqlite3

import pandas as pd
import streamlit as st

from ..config import DB_PATH, HOUSE_PTR_PDF_URL
from ..db import get_connection, init_db
from ..utils import normalize_key

from .constants import (
    COMMITTEES_JSON_PATH,
    NORMALIZED_EXPORT_PATH,
    REVIEW_COLUMNS,
    REVIEW_EXPORT_PATH,
    SQLITE_REVIEW_QUERY,
    SQLITE_TRANSACTION_QUERY,
    TRANSACTION_COLUMNS,
)
from .formatting import format_currency_compact, format_currency_full

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
    from ..polygon_prices import POLYGON_PNL_EXTRA_COLUMNS, enrich_export_rows_with_polygon_pnl

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
    needs = data["sector"].fillna("").astype(str).str.strip().eq("") | data["industry"].fillna("").astype(str).str.strip().eq("")
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
    data["raw_document_path"] = data["raw_document_path"].map(lambda x: "" if pd.isna(x) else str(x).strip())
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
    return format_currency_full(value)


_format_currency_short = format_currency_compact


def _download_bytes(frame: pd.DataFrame) -> bytes:
    buffer = BytesIO()
    frame.to_csv(buffer, index=False)
    return buffer.getvalue()

@st.cache_data(show_spinner=False)
def load_issuer_info(ticker: str) -> dict[str, str]:
    """Return company-level metadata for a ticker from issuers + asset_resolution_cache."""
    t = str(ticker).strip().upper()
    if not t:
        return {}
    conn = get_connection()
    try:
        init_db(conn)
        row = conn.execute(
            """
            SELECT issuer_name, ticker, sector, industry, asset_type
            FROM issuers
            WHERE UPPER(ticker) = ?
            ORDER BY
                CASE WHEN sector <> '' THEN 0 ELSE 1 END,
                CASE WHEN industry <> '' THEN 0 ELSE 1 END
            LIMIT 1
            """,
            (t,),
        ).fetchone()
        if row:
            info = {
                "issuer_name": row["issuer_name"] or "",
                "ticker": row["ticker"] or t,
                "sector": row["sector"] or "",
                "industry": row["industry"] or "",
                "asset_type": row["asset_type"] or "",
            }
        else:
            info = {"issuer_name": "", "ticker": t, "sector": "", "industry": "", "asset_type": ""}

        cache_row = conn.execute(
            """
            SELECT issuer_name, sector, industry, asset_type, resolution_status, match_source
            FROM asset_resolution_cache
            WHERE UPPER(ticker) = ?
            ORDER BY confidence_score DESC
            LIMIT 1
            """,
            (t,),
        ).fetchone()
        if cache_row:
            if not info["issuer_name"] and cache_row["issuer_name"]:
                info["issuer_name"] = cache_row["issuer_name"]
            if not info["sector"] and cache_row["sector"]:
                info["sector"] = cache_row["sector"]
            if not info["industry"] and cache_row["industry"]:
                info["industry"] = cache_row["industry"]
            if not info["asset_type"] and cache_row["asset_type"]:
                info["asset_type"] = cache_row["asset_type"]
            info["resolution_status"] = cache_row["resolution_status"] or ""
            info["match_source"] = cache_row["match_source"] or ""
        else:
            info.setdefault("resolution_status", "")
            info.setdefault("match_source", "")
        return info
    finally:
        conn.close()


_TICKER_DETAILS_TTL = timedelta(days=7)


def _ticker_details_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "name": row["name"] or "",
        "description": row["description"] or "",
        "homepage_url": row["homepage_url"] or "",
        "total_employees": row["total_employees"],
        "market_cap": row["market_cap"],
        "primary_exchange": row["primary_exchange"] or "",
        "sic_description": row["sic_description"] or "",
        "locale": row["locale"] or "",
    }


def _ticker_details_fresh(fetched_at: str | None) -> bool:
    if not fetched_at:
        return False
    raw = str(fetched_at).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            ts = datetime.strptime(raw[:19], fmt)
            return datetime.utcnow() - ts < _TICKER_DETAILS_TTL
        except ValueError:
            continue
    return False


def _polygon_details_to_cache_fields(ticker: str, details: dict[str, Any]) -> dict[str, Any]:
    employees = details.get("total_employees")
    try:
        employees_val = int(employees) if employees is not None else None
    except (TypeError, ValueError):
        employees_val = None
    market_cap = details.get("market_cap")
    try:
        market_cap_val = float(market_cap) if market_cap is not None else None
    except (TypeError, ValueError):
        market_cap_val = None
    return {
        "ticker": ticker,
        "name": str(details.get("name") or "").strip(),
        "description": str(details.get("description") or "").strip(),
        "homepage_url": str(details.get("homepage_url") or "").strip(),
        "total_employees": employees_val,
        "market_cap": market_cap_val,
        "primary_exchange": str(details.get("primary_exchange") or "").strip(),
        "sic_description": str(details.get("sic_description") or "").strip(),
        "locale": str(details.get("locale") or "").strip(),
    }


def _ticker_details_sparse(fields: dict[str, Any]) -> bool:
    if fields.get("market_cap") is not None or fields.get("total_employees") is not None:
        return False
    sic = str(fields.get("sic_description") or "").strip()
    if sic:
        return False
    desc = str(fields.get("description") or "").strip()
    name = str(fields.get("name") or "").strip()
    if len(desc) >= 100 and desc != name:
        return False
    return True


def _fallback_ticker_candidates(ticker: str, polygon: dict[str, Any] | None) -> list[str]:
    """Try shorter symbols / ticker_root when OTC listings lack financials in Polygon."""
    out: list[str] = []
    seen = {ticker}
    if not polygon:
        return out
    root = str(polygon.get("ticker_root") or "").strip().upper()
    if root and root not in seen:
        seen.add(root)
        out.append(root)
    if str(polygon.get("market") or "").lower() == "otc" and len(ticker) > 3:
        for n in range(1, len(ticker) - 2):
            cand = ticker[:-n]
            if cand not in seen:
                seen.add(cand)
                out.append(cand)
    return out[:4]


def _merge_enriched_ticker_fields(primary: dict[str, Any], rich: dict[str, Any]) -> dict[str, Any]:
    out = dict(primary)
    for key in ("description", "homepage_url", "total_employees", "market_cap", "sic_description"):
        if not out.get(key) and rich.get(key):
            out[key] = rich[key]
    return out


def _enrich_sparse_polygon_fields(
    ticker: str,
    fields: dict[str, Any],
    polygon: dict[str, Any],
    *,
    fetch_details,
) -> dict[str, Any]:
    if not _ticker_details_sparse(fields):
        return fields
    for alt in _fallback_ticker_candidates(ticker, polygon):
        alt_poly = fetch_details(alt)
        if not alt_poly:
            continue
        alt_fields = _polygon_details_to_cache_fields(alt, alt_poly)
        if not _ticker_details_sparse(alt_fields):
            return _merge_enriched_ticker_fields(fields, alt_fields)
    return fields


def _upsert_ticker_details_cache(conn: sqlite3.Connection, fields: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO ticker_details_cache (
            ticker, name, description, homepage_url, total_employees,
            market_cap, primary_exchange, sic_description, locale, fetched_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(ticker) DO UPDATE SET
            name=excluded.name,
            description=excluded.description,
            homepage_url=excluded.homepage_url,
            total_employees=excluded.total_employees,
            market_cap=excluded.market_cap,
            primary_exchange=excluded.primary_exchange,
            sic_description=excluded.sic_description,
            locale=excluded.locale,
            fetched_at=datetime('now')
        """,
        (
            fields["ticker"],
            fields["name"],
            fields["description"],
            fields["homepage_url"],
            fields["total_employees"],
            fields["market_cap"],
            fields["primary_exchange"],
            fields["sic_description"],
            fields["locale"],
        ),
    )
    conn.commit()


def load_ticker_details(ticker: str) -> dict[str, Any]:
    """Company profile from Polygon ticker details, cached in SQLite (7-day TTL)."""
    t = str(ticker).strip().upper()
    if not t:
        return {}
    conn = get_connection()
    try:
        init_db(conn)
        row = None
        if _table_exists(conn, "ticker_details_cache"):
            row = conn.execute(
                "SELECT * FROM ticker_details_cache WHERE ticker = ?",
                (t,),
            ).fetchone()
            if row and _ticker_details_fresh(row["fetched_at"]):
                cached = _ticker_details_row_to_dict(row)
                if not _ticker_details_sparse(cached):
                    return cached
        from ..issuer_enrichment import fetch_polygon_ticker_details

        polygon = fetch_polygon_ticker_details(t)
        if polygon:
            fields = _polygon_details_to_cache_fields(t, polygon)
            fields = _enrich_sparse_polygon_fields(
                t, fields, polygon, fetch_details=fetch_polygon_ticker_details
            )
            if _table_exists(conn, "ticker_details_cache"):
                _upsert_ticker_details_cache(conn, fields)
            return {
                k: fields[k]
                for k in (
                    "name",
                    "description",
                    "homepage_url",
                    "total_employees",
                    "market_cap",
                    "primary_exchange",
                    "sic_description",
                    "locale",
                )
            }
        if row:
            return _ticker_details_row_to_dict(row)
        return {}
    finally:
        conn.close()


def _committees_cache_key() -> str:
    if COMMITTEES_JSON_PATH.exists():
        return str(COMMITTEES_JSON_PATH.stat().st_mtime_ns)
    return "missing"


@st.cache_data(show_spinner=False)
def load_committee_assignments(cache_key: str) -> dict[str, list[str]]:
    """Return normalized member name -> committee list from data/committees.json."""
    del cache_key
    if not COMMITTEES_JSON_PATH.exists():
        return {}
    payload = json.loads(COMMITTEES_JSON_PATH.read_text(encoding="utf-8"))
    assignments = payload.get("assignments") or []
    out: dict[str, list[str]] = {}
    for row in assignments:
        if not isinstance(row, dict):
            continue
        name = str(row.get("member_name") or "").strip()
        committees = row.get("committees") or []
        if not name or not isinstance(committees, list):
            continue
        key = normalize_key(name)
        cleaned = [str(c).strip() for c in committees if str(c).strip()]
        if key:
            out[key] = cleaned
    return out


def load_committee_assignments_live() -> dict[str, list[str]]:
    return load_committee_assignments(_committees_cache_key())


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
