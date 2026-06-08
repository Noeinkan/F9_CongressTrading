"""Ticker-level analytics for the API layer.

The ticker→member breakdown lives in :mod:`src.api._patterns_analytics` (shared
with the patterns router); this module adds:

- ``ticker_leaderboard`` — paginated/filterable list of distinct tickers with
  the aggregate KPIs the page header shows.
- ``ticker_profile`` — per-ticker summary block (KPI sparklines, disclosed
  range, buy/sell/call/put counts).
- ``polygon_price_overlay`` — bars + trade markers series for the price chart.

The Polygon cache is read through a local ``load_polygon_bars_live`` helper so
the API does not pull in ``dashboard_shared.data`` (which is wrapped in
``@st.cache_data`` and would re-introduce Streamlit at import time).
"""
from __future__ import annotations

import sqlite3
from typing import Any

import pandas as pd

from ..db import get_connection, init_db
from ._format import format_cumulative_net_label
from ._home_analytics import _dedupe_cumulative_trades
from ._patterns_analytics import add_trade_categories, signed_trade_notional, ticker_member_breakdown
from .repository import transaction_type_display_label


# --------------------------------------------------------------------------- #
# Issuer / ticker details / polygon bars loaders (Streamlit-free ports)
# --------------------------------------------------------------------------- #
def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def load_issuer_info_live(ticker: str) -> dict[str, str]:
    """Best issuer/sector info for a ticker from ``issuers`` + ``asset_resolution_cache``."""
    t = str(ticker).strip().upper()
    if not t:
        return {"issuer_name": "", "ticker": t, "sector": "", "industry": "", "asset_type": "",
                "resolution_status": "", "match_source": ""}
    conn = get_connection()
    try:
        init_db(conn)
        info = {"issuer_name": "", "ticker": t, "sector": "", "industry": "", "asset_type": "",
                "resolution_status": "", "match_source": ""}
        row = None
        if _table_exists(conn, "issuers"):
            row = conn.execute(
                """
                SELECT issuer_name, sector, industry, asset_type
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
            info.update({
                "issuer_name": row["issuer_name"] or "",
                "sector": row["sector"] or "",
                "industry": row["industry"] or "",
                "asset_type": row["asset_type"] or "",
            })
        if _table_exists(conn, "asset_resolution_cache"):
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
        return info
    finally:
        conn.close()


def load_polygon_bars_live(ticker: str) -> pd.DataFrame:
    """Return the cached daily bars for one ticker as a frame (date, close)."""
    t = str(ticker).strip().upper()
    if not t:
        return pd.DataFrame(columns=["date", "close"])
    conn = get_connection()
    try:
        init_db(conn)
        if not _table_exists(conn, "polygon_daily_bar_cache"):
            return pd.DataFrame(columns=["date", "close"])
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


# --------------------------------------------------------------------------- #
# Ticker leaderboard (the page's top section, used as a server-paginated list)
# --------------------------------------------------------------------------- #
def ticker_leaderboard(frame: pd.DataFrame) -> pd.DataFrame:
    """One row per distinct resolved ticker in ``frame``.

    Columns: ``ticker``, ``trades``, ``members``, ``buy``, ``sell``, ``call``,
    ``put``, ``exchange``, ``amount_low``, ``amount_high``, ``first_trade``,
    ``last_trade``, ``issuer_name``, ``sector``.

    The issuer/sector columns are filled best-effort from
    :func:`load_issuer_info_live` so the leaderboard can show a friendly
    name next to each symbol without the frontend doing N+1 lookups.
    """
    if frame.empty or "ticker" not in frame.columns:
        return pd.DataFrame()
    sub = frame.loc[frame["ticker"].astype(str).str.strip() != ""].copy()
    if sub.empty:
        return pd.DataFrame()
    sub = add_trade_categories(sub)
    agg = (
        sub.groupby("ticker", observed=True)
        .agg(
            trades=("ticker", "size"),
            members=("member", "nunique"),
            buy=("is_buy", "sum"),
            sell=("is_sell", "sum"),
            call=("option_side", lambda s: int((s == "Call").sum())),
            put=("option_side", lambda s: int((s == "Put").sum())),
            exchange=("transaction_type", lambda s: int((s.astype(str).str.strip() == "E").sum())),
            amount_low=("amount_low", lambda s: float(pd.to_numeric(s, errors="coerce").sum(skipna=True))),
            amount_high=("amount_high", lambda s: float(pd.to_numeric(s, errors="coerce").sum(skipna=True))),
            first_trade=("transaction_date", "min"),
            last_trade=("transaction_date", "max"),
        )
        .reset_index()
    )
    if "party_label" in sub.columns:
        # Include party mix only when it adds signal — keep it simple: 1 if any Democrat
        # trade, 0 otherwise. (The dashboard's Member-ticker view handles the rest.)
        party_flags = (
            sub.assign(dem=sub["party_label"] == "Democrat")
            .groupby("ticker", observed=True)["dem"]
            .any()
            .astype(bool)
        )
        agg["has_democrat"] = agg["ticker"].map(party_flags).fillna(False)
        party_flags_r = (
            sub.assign(rep=sub["party_label"] == "Republican")
            .groupby("ticker", observed=True)["rep"]
            .any()
            .astype(bool)
        )
        agg["has_republican"] = agg["ticker"].map(party_flags_r).fillna(False)
    agg["issuer_name"] = ""
    agg["sector"] = ""
    for ticker in agg["ticker"]:
        info = load_issuer_info_live(str(ticker))
        agg.loc[agg["ticker"] == ticker, "issuer_name"] = info.get("issuer_name", "")
        agg.loc[agg["ticker"] == ticker, "sector"] = info.get("sector", "")
    return agg.sort_values(["trades", "amount_high"], ascending=[False, False]).reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Per-ticker profile (the second half of the page)
# --------------------------------------------------------------------------- #
def ticker_profile(frame: pd.DataFrame, ticker: str) -> dict[str, Any]:
    """Compute the per-ticker profile payload the frontend renders.

    The shape mirrors the page sections (KPI tiles + member breakdown +
    trade history) but as plain data so the React shell can render it
    with whatever chart library it picks.
    """
    t = str(ticker).strip().upper()
    if not t:
        return {
            "ticker": "",
            "kpis": _empty_profile_kpis(),
            "members": [],
            "transactions": [],
            "ready": False,
        }
    if frame.empty or "ticker" not in frame.columns:
        return {
            "ticker": t,
            "kpis": _empty_profile_kpis(t),
            "members": [],
            "transactions": [],
            "ready": False,
        }
    sub = frame.loc[frame["ticker"].astype(str).str.upper() == t].copy()
    if sub.empty:
        return {
            "ticker": t,
            "kpis": _empty_profile_kpis(t),
            "members": [],
            "transactions": [],
            "ready": False,
        }
    sub = add_trade_categories(sub)
    buys = int(sub["is_buy"].sum())
    sells = int(sub["is_sell"].sum())
    calls = int((sub["option_side"] == "Call").sum())
    puts = int((sub["option_side"] == "Put").sum())
    exchanges = int((sub["transaction_type"].astype(str).str.strip() == "E").sum())
    amount_low_total = float(pd.to_numeric(sub["amount_low"], errors="coerce").sum(skipna=True))
    amount_high_total = float(pd.to_numeric(sub["amount_high"], errors="coerce").sum(skipna=True))
    first_trade = sub["transaction_date"].min()
    last_trade = sub["transaction_date"].max()
    members = sub["member"].nunique()

    members_df = ticker_member_breakdown(frame, t)
    if not members_df.empty:
        members_df = members_df.assign(
            disclosed_range=_disclosed_range_series(
                members_df["amount_low_sum"], members_df["amount_high_sum"]
            )
        )

    tx_columns = [
        "member", "chamber", "party", "ticker", "transaction_type", "transaction_type_label",
        "transaction_date", "filing_date", "amount_low", "amount_high", "amount_range_raw",
        "issuer_name", "asset_name_raw", "disclosure_url",
    ]
    tx_df = sub.sort_values(["transaction_date", "member"], ascending=[False, True]).copy()
    if "transaction_type_label" not in tx_df.columns:
        tx_df["transaction_type_label"] = tx_df["transaction_type"].map(transaction_type_display_label)

    kpis = {
        "ticker": t,
        "trades": int(len(sub)),
        "members": int(members),
        "buy": buys,
        "sell": sells,
        "call": calls,
        "put": puts,
        "exchange": exchanges,
        "amount_low_total": amount_low_total,
        "amount_high_total": amount_high_total,
        "first_trade": first_trade,
        "last_trade": last_trade,
    }
    return {
        "ticker": t,
        "kpis": kpis,
        "members": members_df,
        "transactions": tx_df,
        "ready": True,
    }


def _empty_profile_kpis(ticker: str = "") -> dict[str, Any]:
    return {
        "ticker": ticker,
        "trades": 0,
        "members": 0,
        "buy": 0,
        "sell": 0,
        "call": 0,
        "put": 0,
        "exchange": 0,
        "amount_low_total": 0.0,
        "amount_high_total": 0.0,
        "first_trade": None,
        "last_trade": None,
    }


def _disclosed_range_series(low: pd.Series, high: pd.Series) -> list[str]:
    from ._format import format_disclosed_range

    out: list[str] = []
    for lo, hi in zip(
        pd.to_numeric(low, errors="coerce"),
        pd.to_numeric(high, errors="coerce"),
        strict=True,
    ):
        out.append(format_disclosed_range(lo, hi))
    return out


# --------------------------------------------------------------------------- #
# Price overlay (Polygon bars + trade markers)
# --------------------------------------------------------------------------- #
def polygon_price_overlay(
    frame: pd.DataFrame, ticker: str
) -> dict[str, Any]:
    """Series for the price-and-trade overlay chart.

    Returns bars (``{date, close}``) and trade markers (one per disclosure
    row for the ticker). The y-value of each trade marker is the bar close
    on or before the trade date — the same convention
    ``dashboard_shared.charts.build_price_overlay_figure`` uses.
    """
    t = str(ticker).strip().upper()
    if not t:
        return {"ticker": "", "bars": [], "trades": [], "ready": False}
    bars = load_polygon_bars_live(t)
    sub = frame.loc[frame["ticker"].astype(str).str.upper() == t].dropna(
        subset=["transaction_date"]
    ).copy() if not frame.empty else pd.DataFrame()
    if bars.empty and sub.empty:
        return {"ticker": t, "bars": [], "trades": [], "ready": False}

    bar_records: list[dict[str, Any]] = []
    if not bars.empty:
        bar_dates = pd.to_datetime(bars["date"], errors="coerce")
        for d, c in zip(bar_dates, bars["close"], strict=True):
            if pd.isna(d):
                continue
            bar_records.append({"date": d.strftime("%Y-%m-%d"), "close": float(c)})

    trade_records: list[dict[str, Any]] = []
    if not sub.empty:
        bars_sorted = (
            bars.assign(date=pd.to_datetime(bars["date"], errors="coerce"))
            .dropna(subset=["date"])
            .sort_values("date")
            if not bars.empty
            else pd.DataFrame()
        )
        for _, row in sub.iterrows():
            td = row["transaction_date"]
            y_val: float | None = None
            if not bars_sorted.empty:
                eligible = bars_sorted.loc[bars_sorted["date"] <= td, "close"]
                if not eligible.empty:
                    y_val = float(eligible.iloc[-1])
            if y_val is None and not bars_sorted.empty:
                y_val = float(bars_sorted["close"].iloc[0])
            trade_records.append(
                {
                    "transaction_date": pd.Timestamp(td).strftime("%Y-%m-%d"),
                    "y": y_val,
                    "member": str(row.get("member", "")),
                    "transaction_type": str(row.get("transaction_type", "")).strip(),
                    "transaction_type_label": transaction_type_display_label(
                        row.get("transaction_type")
                    ),
                }
            )

    return {
        "ticker": t,
        "bars": bar_records,
        "trades": trade_records,
        "ready": True,
    }


def ticker_member_timeline_payload(frame: pd.DataFrame, ticker: str) -> dict[str, object]:
    """Scatter rows for the ticker member-timeline chart (y = member).

    Mirrors ``dashboard_shared.charts._build_ticker_member_timeline``.
    """
    t = str(ticker).strip().upper()
    if not t:
        return {"ticker": "", "members": [], "rows": []}

    sub = frame.loc[frame["ticker"].astype(str).str.upper() == t].copy()
    sub = sub.dropna(subset=["transaction_date"])
    if sub.empty:
        return {"ticker": t, "members": [], "rows": []}

    member_order = (
        sub.groupby("member", observed=True)["transaction_date"]
        .max()
        .sort_values(ascending=False)
        .index.tolist()
    )

    sub = sub.copy()
    sub["transaction_type_label"] = sub["transaction_type"].map(transaction_type_display_label)
    cols = [
        "member",
        "transaction_date",
        "transaction_type",
        "transaction_type_label",
        "amount_range_raw",
        "issuer_name",
        "chamber",
    ]
    present = [c for c in cols if c in sub.columns]
    out = sub[present].sort_values(["transaction_date", "member"], ascending=[True, True])

    rows: list[dict[str, object]] = []
    for _, row in out.iterrows():
        rec: dict[str, object] = {}
        for col in present:
            val = row[col]
            if col == "transaction_date" and pd.notna(val):
                rec[col] = pd.Timestamp(val).strftime("%Y-%m-%d")
            else:
                rec[col] = val if not (isinstance(val, float) and pd.isna(val)) else None
        rows.append(rec)

    return {
        "ticker": t,
        "members": [str(m) for m in member_order],
        "rows": rows,
    }


def ticker_cumulative_exposure_payload(
    frame: pd.DataFrame, ticker: str, *, top_n: int = 16
) -> dict[str, object]:
    """Faceted cumulative net exposure rows for one ticker.

    Mirrors ``dashboard_shared.charts._build_member_cumulative_notional_chart``.
    """
    t = str(ticker).strip().upper()
    if not t:
        return {"ticker": "", "members": [], "truncated": False, "rows": []}

    sub = frame.loc[frame["ticker"].astype(str).str.upper() == t].copy()
    sub = sub.dropna(subset=["transaction_date"])
    if sub.empty:
        return {"ticker": t, "members": [], "truncated": False, "rows": []}

    sub = _dedupe_cumulative_trades(sub)
    sub["_signed"] = sub.apply(signed_trade_notional, axis=1)
    member_counts = sub["member"].value_counts()
    total_members = len(member_counts)
    truncated = total_members > top_n
    member_order = member_counts.head(top_n).index.tolist()
    sub = sub[sub["member"].isin(member_order)]
    if sub.empty:
        return {"ticker": t, "members": [], "truncated": truncated, "rows": []}

    sub = sub.sort_values(["member", "transaction_date", "filing_date"], ascending=[True, True, True])
    sub["cumulative_net"] = sub.groupby("member", observed=True)["_signed"].cumsum()

    rows: list[dict[str, object]] = []
    for _, row in sub.iterrows():
        cum = float(row["cumulative_net"])
        rows.append(
            {
                "member": str(row["member"]),
                "transaction_date": pd.Timestamp(row["transaction_date"]).strftime("%Y-%m-%d"),
                "cumulative_net": cum,
                "cumulative_label": format_cumulative_net_label(cum),
                "txn_type_label": transaction_type_display_label(row.get("transaction_type")),
                "amount_range_raw": str(row.get("amount_range_raw") or ""),
            }
        )

    return {
        "ticker": t,
        "members": [str(m) for m in member_order],
        "truncated": truncated,
        "rows": rows,
    }
