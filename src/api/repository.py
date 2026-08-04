"""Data access for the API layer.

Loads and prepares normalized transactions and the review queue from SQLite.
Uses an in-process memo keyed on source-file mtimes so repeated requests do
not re-read the database.
"""
from __future__ import annotations

import re
import sqlite3
from datetime import date
from pathlib import Path
from threading import Lock
from typing import Optional

import pandas as pd

from ..config import DB_PATH, HOUSE_PTR_PDF_URL
from ..db import get_connection, init_db, upsert_asset_resolution, upsert_issuer
from ..utils import coerce_amount_bounds, normalize_whitespace
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


def _normalize_transaction_type(raw: object) -> str:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return ""
    return str(raw).strip()


def is_buy_transaction_type(raw: object) -> bool:
    """True for House ``P`` and OGE ``P (Buy)`` (and similar purchase labels)."""
    tt = _normalize_transaction_type(raw)
    if not tt:
        return False
    upper = tt.upper()
    if upper == "P" or upper.startswith("P ") or upper.startswith("P("):
        return True
    return "BUY" in upper or "PURCHASE" in upper


def is_sell_transaction_type(raw: object) -> bool:
    """True for House ``S`` / ``S (partial)`` and OGE ``S (Sell)``."""
    tt = _normalize_transaction_type(raw)
    if not tt:
        return False
    upper = tt.upper()
    return upper == "S" or upper.startswith("S ") or upper.startswith("S(") or "SELL" in upper


def is_exchange_transaction_type(raw: object) -> bool:
    """True for House ``E`` and OGE ``E (Exchange)``."""
    tt = _normalize_transaction_type(raw)
    if not tt:
        return False
    upper = tt.upper()
    if upper == "E" or upper.startswith("E ") or upper.startswith("E("):
        return True
    return "EXCHANGE" in upper


def transaction_type_display_label(raw: object) -> str:
    s = _normalize_transaction_type(raw)
    if not s or s.lower() == "unknown":
        return "Unknown"
    mapping = {
        "P": "Buy",
        "S": "Sell",
        "S (partial)": "Sell (partial)",
        "E": "Exchange",
        "P (Buy)": "Buy",
        "S (Sell)": "Sell",
        "E (Exchange)": "Exchange",
    }
    if s in mapping:
        return mapping[s]
    # OGE / free-text variants: classify then map to a short label.
    if is_buy_transaction_type(s):
        return "Buy"
    if is_sell_transaction_type(s):
        if "partial" in s.lower():
            return "Sell (partial)"
        return "Sell"
    if is_exchange_transaction_type(s):
        return "Exchange"
    return s


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
    # Re-parse / repair disclosure bounds from amount_range_raw so cents-as-high
    # ("$584.22" → 584/22) and truncated bucket highs ("$15,001 - 5") do not
    # poison signed notional, KPI sums, or cumulative exposure bands.
    if "amount_range_raw" in data.columns and len(data):
        raw_before_lo = data["amount_low"].to_numpy(copy=True)
        raw_before_hi = data["amount_high"].to_numpy(copy=True)
        repaired = [
            coerce_amount_bounds(lo, hi, raw)
            for lo, hi, raw in zip(
                data["amount_low"],
                data["amount_high"],
                data["amount_range_raw"],
                strict=True,
            )
        ]
        data["amount_low"] = [pair[0] for pair in repaired]
        data["amount_high"] = [pair[1] for pair in repaired]
        # #region agent log
        try:
            import json
            import time
            from pathlib import Path

            changed = sum(
                1
                for (lo, hi), blo, bhi in zip(repaired, raw_before_lo, raw_before_hi, strict=True)
                if lo != blo or hi != bhi
            )
            inverted_before = int(
                sum(
                    1
                    for blo, bhi in zip(raw_before_lo, raw_before_hi, strict=True)
                    if pd.notna(blo) and pd.notna(bhi) and float(blo) > float(bhi)
                )
            )
            lo_after = pd.to_numeric(data["amount_low"], errors="coerce")
            hi_after = pd.to_numeric(data["amount_high"], errors="coerce")
            inverted_after = int(((lo_after.notna() & hi_after.notna()) & (lo_after > hi_after)).sum())
            with (Path(__file__).resolve().parents[2] / "debug-ce707b.log").open(
                "a", encoding="utf-8"
            ) as _fh:
                _fh.write(
                    json.dumps(
                        {
                            "sessionId": "ce707b",
                            "runId": "post-fix",
                            "hypothesisId": "D",
                            "location": "repository.py:_prepare_transactions",
                            "message": "amount_bound_repair",
                            "data": {
                                "rows": int(len(data)),
                                "changed": int(changed),
                                "inverted_before": inverted_before,
                                "inverted_after": inverted_after,
                            },
                            "timestamp": int(time.time() * 1000),
                        }
                    )
                    + "\n"
                )
        except Exception:
            pass
        # #endregion
    data["ticker"] = data["ticker"].fillna("").astype(str).str.upper()
    data["member"] = data["member"].fillna("Unknown")
    data["party"] = data["party"].fillna("")
    data["state"] = data["state"].fillna("")
    # Overlay blank party from vendors legislators map so Patterns bipartisan
    # (and party filters) work even before / without a DB backfill.
    blank_party = data["party"].astype(str).str.strip() == ""
    if blank_party.any():
        from ..member_parties import get_party_lookup, resolve_party_for_row

        lookup = get_party_lookup()
        chamber_col = data["chamber"] if "chamber" in data.columns else ""
        state_col = data["state"]
        filled = [
            resolve_party_for_row(
                str(member),
                chamber=str(chamber) if chamber is not None else "",
                state=str(state) if state is not None else "",
                lookup=lookup,
            )
            if is_blank
            else ""
            for member, chamber, state, is_blank in zip(
                data["member"],
                chamber_col if isinstance(chamber_col, pd.Series) else [""] * len(data),
                state_col,
                blank_party,
                strict=True,
            )
        ]
        if any(filled):
            party_series = data["party"].astype(str)
            overlay = pd.Series(filled, index=data.index)
            data["party"] = party_series.where(~blank_party | (overlay == ""), overlay)
    data["issuer_name"] = data["issuer_name"].fillna("")
    data["sector"] = data["sector"].fillna("").astype(str).str.strip()
    data["industry"] = data["industry"].fillna("").astype(str).str.strip()
    data["asset_name_normalized"] = data["asset_name_normalized"].fillna("")
    data["asset_name_raw"] = data["asset_name_raw"].fillna("")
    data["owner_type"] = data["owner_type"].fillna("unspecified")
    data["review_status"] = data["review_status"].fillna("pending")
    data["asset_type"] = data["asset_type"].fillna("unknown")
    # Annuities (RILA / VA) are sometimes fuzzy-matched onto the insurer's
    # equity ticker; strip that so they cannot appear on ticker flow charts.
    annuity_mask = data["asset_type"].astype(str).str.strip().str.lower().eq("annuity")
    if annuity_mask.any():
        data.loc[annuity_mask, "ticker"] = ""
    data["transaction_type"] = data["transaction_type"].fillna("unknown")
    data["transaction_type_label"] = data["transaction_type"].map(transaction_type_display_label)
    data["month"] = data["transaction_date"].dt.to_period("M").dt.to_timestamp()
    data["doc_id"] = data["doc_id"].map(lambda x: "" if pd.isna(x) else str(x).strip())
    if "source_hash" in data.columns:
        data["source_hash"] = data["source_hash"].map(
            lambda x: "" if pd.isna(x) else str(x).strip()
        )
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
    data["transaction_id"] = pd.to_numeric(data["transaction_id"], errors="coerce")
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


def invalidate_data_cache() -> None:
    """Drop in-process transaction/review memo after SQLite mutations.

    Needed because WAL writes may not bump the main DB file mtime that
    :func:`_data_cache_key` watches.
    """
    global _cache_key, _cache_transactions, _cache_review
    with _cache_lock:
        _cache_key = None
        _cache_transactions = None
        _cache_review = None


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
    """Calendar years included for a given lookback window (None = all).

    Uses today's calendar year as the anchor. When that window is entirely
    ahead of the data (e.g. only 2025 transaction dates with lookback=1 in
    2026), fall back to the newest ``n_years`` of available years so pages
    with sparse/lagged dates are not blanked.
    """
    if n_years is None:
        return years_available
    if not years_available:
        return []
    current_year = date.today().year
    cutoff_year = current_year - n_years + 1
    selected = [y for y in years_available if y >= cutoff_year]
    if selected:
        return selected
    newest = sorted(years_available, reverse=True)[:n_years]
    return sorted(newest)


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


# --------------------------------------------------------------------------- #
# Review-queue triage mutations (manual resolve / dismiss)
# --------------------------------------------------------------------------- #
_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,15}$")


def normalize_manual_ticker(ticker: str | None) -> str:
    """Uppercase/trim a manual ticker; empty string when missing."""
    return normalize_whitespace(ticker or "").upper()


def _assert_sqlite_review_source() -> None:
    """Mutations only work against the live SQLite review_queue."""
    _, source = load_review_queue(load_transactions()[0])
    if not str(source).startswith("sqlite:"):
        raise RuntimeError(
            f"Review triage requires a SQLite review_queue (current source: {source})"
        )


def _apply_resolved_ticker(
    conn: sqlite3.Connection,
    *,
    transaction_id: int,
    ticker: str,
    asset_name_raw: str,
    asset_name_normalized: str,
    asset_type: str,
    apply_to_asset: bool,
) -> int:
    """Update one transaction (+ optional same-asset siblings) and clear queue rows.

    Returns the number of transactions updated.
    """
    issuer_name = asset_name_normalized or asset_name_raw or ticker
    issuer_id = upsert_issuer(
        conn,
        issuer_name=issuer_name,
        ticker=ticker,
        asset_type=asset_type or "",
        commit=False,
    )

    target_ids = [transaction_id]
    if apply_to_asset and asset_name_raw:
        sibling_rows = conn.execute(
            """
            SELECT t.id
            FROM transactions t
            JOIN review_queue rq ON rq.transaction_id = t.id
            WHERE t.asset_name_raw = ? AND t.id <> ?
            """,
            (asset_name_raw, transaction_id),
        ).fetchall()
        target_ids.extend(int(r["id"]) for r in sibling_rows)

    for tid in target_ids:
        conn.execute(
            """
            UPDATE transactions
            SET ticker = ?,
                issuer_id = ?,
                confidence_score = 1.0,
                review_status = 'exact_match',
                updated_at = datetime('now')
            WHERE id = ?
            """,
            (ticker, issuer_id, tid),
        )
        conn.execute("DELETE FROM review_queue WHERE transaction_id = ?", (tid,))

    if apply_to_asset and asset_name_raw:
        upsert_asset_resolution(
            conn,
            asset_name_raw=asset_name_raw,
            asset_name_normalized=asset_name_normalized or asset_name_raw,
            issuer_name=issuer_name,
            ticker=ticker,
            cusip_or_figi="",
            asset_type=asset_type or "",
            sector="",
            industry="",
            confidence_score=1.0,
            resolution_status="exact_match",
            match_source="manual_review",
            commit=False,
        )

    return len(target_ids)


def resolve_review_transaction(
    transaction_id: int,
    *,
    ticker: str | None,
    apply_to_asset: bool = False,
) -> dict[str, object]:
    """Assign a ticker, mark ``exact_match``, and remove the row from review_queue."""
    ticker_value = normalize_manual_ticker(ticker)
    if not ticker_value:
        raise ValueError("ticker is required")
    if not _TICKER_RE.match(ticker_value):
        raise ValueError("ticker must look like a symbol (e.g. AAPL, BRK.B)")

    _assert_sqlite_review_source()
    conn = get_connection()
    try:
        init_db(conn)
        queued = conn.execute(
            "SELECT 1 FROM review_queue WHERE transaction_id = ?",
            (transaction_id,),
        ).fetchone()
        if queued is None:
            raise KeyError(f"transaction {transaction_id} is not in the review queue")

        row = conn.execute(
            """
            SELECT id, asset_name_raw, asset_name_normalized, asset_type, ticker
            FROM transactions
            WHERE id = ?
            """,
            (transaction_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"transaction {transaction_id} not found")

        updated = _apply_resolved_ticker(
            conn,
            transaction_id=transaction_id,
            ticker=ticker_value,
            asset_name_raw=normalize_whitespace(row["asset_name_raw"] or ""),
            asset_name_normalized=normalize_whitespace(row["asset_name_normalized"] or ""),
            asset_type=normalize_whitespace(row["asset_type"] or ""),
            apply_to_asset=apply_to_asset,
        )
        conn.commit()
    finally:
        conn.close()

    invalidate_data_cache()
    return {
        "ok": True,
        "action": "resolve",
        "transaction_id": transaction_id,
        "ticker": ticker_value,
        "updated_count": updated,
        "apply_to_asset": apply_to_asset,
    }


def accept_review_transaction(
    transaction_id: int,
    *,
    apply_to_asset: bool = False,
) -> dict[str, object]:
    """Promote the transaction's current ticker to ``exact_match`` and clear the queue row."""
    _assert_sqlite_review_source()
    conn = get_connection()
    try:
        init_db(conn)
        row = conn.execute(
            "SELECT ticker FROM transactions WHERE id = ?",
            (transaction_id,),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        raise KeyError(f"transaction {transaction_id} not found")
    ticker = normalize_manual_ticker(row["ticker"])
    if not ticker:
        raise ValueError(
            "transaction has no ticker to accept; use resolve with an explicit ticker"
        )
    result = resolve_review_transaction(
        transaction_id,
        ticker=ticker,
        apply_to_asset=apply_to_asset,
    )
    result["action"] = "accept"
    return result


def dismiss_review_transaction(transaction_id: int) -> dict[str, object]:
    """Remove a row from the review queue without changing the transaction ticker."""
    _assert_sqlite_review_source()
    conn = get_connection()
    try:
        init_db(conn)
        queued = conn.execute(
            "SELECT 1 FROM review_queue WHERE transaction_id = ?",
            (transaction_id,),
        ).fetchone()
        if queued is None:
            raise KeyError(f"transaction {transaction_id} is not in the review queue")

        conn.execute("DELETE FROM review_queue WHERE transaction_id = ?", (transaction_id,))
        conn.commit()
    finally:
        conn.close()

    invalidate_data_cache()
    return {
        "ok": True,
        "action": "dismiss",
        "transaction_id": transaction_id,
    }
