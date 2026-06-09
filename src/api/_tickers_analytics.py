"""Ticker-level analytics for the API layer.

The ticker→member breakdown lives in :mod:`src.api._patterns_analytics` (shared
with the patterns router); this module adds:

- ``ticker_leaderboard`` — paginated/filterable list of distinct tickers with
  the aggregate KPIs the page header shows.
- ``ticker_profile`` — per-ticker summary block (KPI sparklines, disclosed
  range, buy/sell/call/put counts).
- ``polygon_price_overlay`` — bars + trade markers series for the price chart.
- ``trade_return_metrics`` — per-trade price/return numbers derived from the
  local Polygon daily bar cache (no network calls), so the profile / leaderboard
  can show a "return since trade" column even when offline.

The Polygon cache is read through a local ``load_polygon_bars_live`` helper so
the API does not pull in ``dashboard_shared.data`` (which is wrapped in
``@st.cache_data`` and would re-introduce Streamlit at import time).
"""
from __future__ import annotations

import sqlite3
from datetime import date
from threading import Lock
from typing import Any, Optional

import pandas as pd

from ..db import get_connection, init_db
from ..utils import is_non_equity_asset
from ._format import format_cumulative_net_label
from ._home_analytics import _dedupe_cumulative_trades
from ._patterns_analytics import add_trade_categories, signed_trade_notional, ticker_member_breakdown
from .repository import _data_cache_key, transaction_type_display_label


# --------------------------------------------------------------------------- #
# Issuer / ticker details / polygon bars loaders (Streamlit-free ports)
# --------------------------------------------------------------------------- #
def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _fetch_issuer_info_bulk(tickers: list[str]) -> dict[str, dict[str, str]]:
    """Load issuer/sector metadata for a batch of tickers in two SQL roundtrips.

    Returns ``{ticker: {issuer_name, sector, industry, asset_type, ...}}`` for
    every requested ticker. The earlier per-ticker loop on the leaderboard did
    two queries per ticker (~2000 round-trips on a 1.5K-ticker dataset); this
    collapses it to a single ``IN (...)`` against ``issuers`` and another
    against ``asset_resolution_cache`` — the same merge logic the row-level
    helper used, just vectorised.
    """
    cleaned = sorted({str(t).strip().upper() for t in tickers if str(t).strip()})
    if not cleaned:
        return {}
    out: dict[str, dict[str, str]] = {
        t: {
            "issuer_name": "",
            "ticker": t,
            "sector": "",
            "industry": "",
            "asset_type": "",
            "resolution_status": "",
            "match_source": "",
        }
        for t in cleaned
    }
    placeholders = ",".join("?" for _ in cleaned)
    conn = get_connection()
    try:
        init_db(conn)
        if _table_exists(conn, "issuers"):
            # Prefer the row with the most non-empty metadata for each ticker.
            rows = conn.execute(
                f"""
                SELECT UPPER(ticker) AS ticker, issuer_name, sector, industry, asset_type
                FROM issuers
                WHERE UPPER(ticker) IN ({placeholders})
                  AND COALESCE(ticker, '') <> ''
                ORDER BY
                    CASE WHEN sector <> '' THEN 0 ELSE 1 END,
                    CASE WHEN industry <> '' THEN 0 ELSE 1 END
                """,
                cleaned,
            ).fetchall()
            for row in rows:
                t = str(row["ticker"]).strip().upper()
                if t not in out:
                    continue
                info = out[t]
                # Don't downgrade a non-empty value with a later empty one.
                if not info["issuer_name"] and row["issuer_name"]:
                    info["issuer_name"] = row["issuer_name"]
                if not info["sector"] and row["sector"]:
                    info["sector"] = row["sector"]
                if not info["industry"] and row["industry"]:
                    info["industry"] = row["industry"]
                if not info["asset_type"] and row["asset_type"]:
                    info["asset_type"] = row["asset_type"]
        if _table_exists(conn, "asset_resolution_cache"):
            rows = conn.execute(
                f"""
                SELECT UPPER(ticker) AS ticker, issuer_name, sector, industry, asset_type,
                       resolution_status, match_source
                FROM asset_resolution_cache
                WHERE UPPER(ticker) IN ({placeholders})
                  AND COALESCE(ticker, '') <> ''
                ORDER BY confidence_score DESC
                """,
                cleaned,
            ).fetchall()
            for row in rows:
                t = str(row["ticker"]).strip().upper()
                if t not in out:
                    continue
                info = out[t]
                if not info["issuer_name"] and row["issuer_name"]:
                    info["issuer_name"] = row["issuer_name"]
                if not info["sector"] and row["sector"]:
                    info["sector"] = row["sector"]
                if not info["industry"] and row["industry"]:
                    info["industry"] = row["industry"]
                if not info["asset_type"] and row["asset_type"]:
                    info["asset_type"] = row["asset_type"]
                info["resolution_status"] = row["resolution_status"] or ""
                info["match_source"] = row["match_source"] or ""
    finally:
        conn.close()
    return out


def _fetch_polygon_bars_bulk(tickers: list[str]) -> dict[str, list[tuple[date, float]]]:
    """Load cached daily bars for many tickers in a single SQL roundtrip.

    Returns ``{ticker: [(date, close), ...]}`` sorted by date. Tickers absent
    from the cache map to an empty list. ``close <= 0`` rows are dropped (they
    represent delisted/suspended sessions that would poison the return math).
    """
    cleaned = sorted({str(t).strip().upper() for t in tickers if str(t).strip()})
    if not cleaned:
        return {}
    out: dict[str, list[tuple[date, float]]] = {t: [] for t in cleaned}
    placeholders = ",".join("?" for _ in cleaned)
    conn = get_connection()
    try:
        init_db(conn)
        if not _table_exists(conn, "polygon_daily_bar_cache"):
            return out
        rows = conn.execute(
            f"""
            SELECT UPPER(ticker) AS ticker, bar_date, close
            FROM polygon_daily_bar_cache
            WHERE UPPER(ticker) IN ({placeholders})
            ORDER BY ticker, bar_date
            """,
            cleaned,
        ).fetchall()
    finally:
        conn.close()
    for row in rows:
        t = str(row["ticker"]).strip().upper()
        if t not in out:
            continue
        try:
            d = pd.Timestamp(row["bar_date"]).date()
        except (TypeError, ValueError):
            continue
        try:
            c = float(row["close"])
        except (TypeError, ValueError):
            continue
        if d and c > 0:
            out[t].append((d, c))
    return out


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


def _median_amount(low: Any, high: Any) -> float | None:
    """Mirror of the helper in :mod:`src.polygon_prices` — single midpoint
    of the disclosed bucket, used for the per-trade estimated dollar PnL.
    """
    vals: list[float] = []
    for v in (low, high):
        if v is None:
            continue
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        if fv > 0:
            vals.append(fv)
    if not vals:
        return None
    vals.sort()
    mid = len(vals) // 2
    if len(vals) % 2:
        return vals[mid]
    return (vals[mid - 1] + vals[mid]) / 2.0


def _resolve_session_close(bars: list[tuple[date, float]], target: date) -> tuple[float, date] | None:
    """Same calendar session, else first session after target, else last before.

    Always returns ``(close, session_date)`` — the price first, the trading
    session date second — so callers can unpack ``pt, session = hit`` and feed
    ``pt`` straight into the return math.
    """
    if not bars:
        return None
    for d, c in bars:
        if d == target:
            return (c, d)
    after = [(d, c) for d, c in bars if d > target]
    if after:
        d, c = after[0]
        return (c, d)
    before = [(d, c) for d, c in bars if d < target]
    if before:
        d, c = before[-1]
        return (c, d)
    return None


def _signed_return(
    transaction_type: str,
    price_trade: float,
    price_asof: float,
    median_notional: float | None,
) -> tuple[float | None, float | None]:
    """Return (return_pct, est_pnl_usd) using the same sign convention as the
    CSV export: a buy is a long position (positive return = profit), a sell
    represents a position exit (the sign is flipped because the filer keeps
    the price move in the opposite direction).
    """
    if price_trade <= 0 or price_asof <= 0:
        return None, None
    mkt_ret = price_asof / price_trade - 1.0
    ret_pct = mkt_ret * 100.0
    if median_notional is None or median_notional <= 0:
        return ret_pct, None
    tt = (transaction_type or "").strip()
    if tt == "P":
        return ret_pct, median_notional * mkt_ret
    if tt.startswith("S"):
        return ret_pct, -median_notional * mkt_ret
    return ret_pct, None


def _metrics_from_bars(
    transactions: pd.DataFrame,
    pairs: list[tuple[date, float]],
    *,
    as_of: date | None = None,
) -> list[dict[str, Any]]:
    """Same output shape as :func:`trade_return_metrics` but takes pre-loaded bars.

    Splits the per-trade loop away from the I/O so the leaderboard can call
    it once per ticker with the bars it already pulled in a single batched
    query, instead of one ``load_polygon_bars_live`` per ticker.
    """
    if transactions.empty:
        return []

    def _is_non_equity_row(row: pd.Series) -> bool:
        return bool(
            is_non_equity_asset(
                str(row.get("ticker") or ""),
                str(row.get("asset_name_raw") or ""),
            )
        )

    non_equity_flags = [
        _is_non_equity_row(row) for row in transactions.to_dict("records")
    ]

    if not pairs or transactions["ticker"].astype(str).str.strip().eq("").all():
        return [{"is_non_equity": ne} for ne in non_equity_flags]

    target = as_of or date.today()
    asof_hit = _resolve_session_close(pairs, target)
    if asof_hit is None:
        return [{"is_non_equity": ne} for ne in non_equity_flags]
    pa, session_asof = asof_hit

    out: list[dict[str, Any]] = []
    for row, is_ne in zip(transactions.to_dict("records"), non_equity_flags, strict=True):
        td_raw = row.get("transaction_date")
        if pd.isna(td_raw):
            out.append({"is_non_equity": is_ne})
            continue
        td = pd.Timestamp(td_raw).date()
        trade_hit = _resolve_session_close(pairs, td)
        if trade_hit is None:
            out.append({"is_non_equity": is_ne})
            continue
        pt, session_trade = trade_hit
        median = _median_amount(row.get("amount_low"), row.get("amount_high"))
        ret_pct, pnl = _signed_return(str(row.get("transaction_type") or "").strip(), pt, pa, median)
        out.append(
            {
                "price_trade": f"{pt:.6g}",
                "price_session": session_trade.isoformat(),
                "price_asof": f"{pa:.6g}",
                "price_asof_session": session_asof.isoformat(),
                "return_pct": round(ret_pct, 4) if ret_pct is not None else None,
                "est_pnl_usd": round(pnl, 2) if pnl is not None else None,
                "is_non_equity": is_ne,
            }
        )
    return out


def trade_return_metrics(
    transactions: pd.DataFrame,
    *,
    as_of: date | None = None,
) -> list[dict[str, Any]]:
    """Per-trade return metrics derived from the local Polygon cache only.

    Returns one record per transaction row (in input order) with:

    - ``price_trade`` / ``price_session``: the close on the trade date (or the
      closest session on either side when the exact date is missing).
    - ``price_asof`` / ``price_asof_session``: the close on ``as_of`` (default
      today, or the most recent cached bar if today is missing).
    - ``return_pct``: percentage move from trade date to as-of date.
    - ``est_pnl_usd``: signed dollar PnL using the disclosed bucket midpoint.
    - ``is_non_equity``: True when the asset has no continuous market price
      (Treasury notes, municipal / corporate bonds, bond funds, etc.) so the
      frontend can render an explicit "n/a" label instead of an empty "—".

    All price/return fields are ``None`` when the cache has no usable bars
    for the ticker, so the frontend can render an "—" without a special case.
    The ``is_non_equity`` flag is always populated from the asset metadata.
    """
    if transactions.empty:
        return []

    bars = load_polygon_bars_live(str(transactions["ticker"].iloc[0]).strip().upper())
    pairs: list[tuple[date, float]] = []
    if not bars.empty:
        bar_dates = pd.to_datetime(bars["date"], errors="coerce")
        bar_closes = pd.to_numeric(bars["close"], errors="coerce")
        for d, c in zip(bar_dates, bar_closes, strict=True):
            if pd.isna(d) or pd.isna(c) or float(c) <= 0:
                continue
            pairs.append((pd.Timestamp(d).date(), float(c)))
        pairs.sort(key=lambda x: x[0])

    return _metrics_from_bars(transactions, pairs, as_of=as_of)


def weighted_aggregate_return(metrics: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Collapse a list of per-trade return records into a single weighted
    return: each trade's return is weighted by the absolute estimated PnL
    (so tiny ``$1K`` swings don't drown out a ``$50K`` winner). Falls back to
    the simple mean when no PnL is available.

    Returns ``None`` when no trade had both prices; otherwise returns a dict
    with ``return_pct`` (weighted) and ``trade_count``.
    """
    usable = [m for m in metrics if m.get("return_pct") is not None]
    if not usable:
        return None
    weights = [abs(m["est_pnl_usd"]) if m.get("est_pnl_usd") else 1.0 for m in usable]
    total_w = sum(weights)
    if total_w <= 0:
        return {"return_pct": round(sum(m["return_pct"] for m in usable) / len(usable), 4),
                "trade_count": len(usable)}
    weighted = sum(m["return_pct"] * w for m, w in zip(usable, weights, strict=True)) / total_w
    return {"return_pct": round(weighted, 4), "trade_count": len(usable)}


# --------------------------------------------------------------------------- #
# Ticker leaderboard (the page's top section, used as a server-paginated list)
# --------------------------------------------------------------------------- #
def ticker_leaderboard(frame: pd.DataFrame) -> pd.DataFrame:
    """One row per distinct resolved ticker in ``frame``.

    Columns: ``ticker``, ``trades``, ``members``, ``buy``, ``sell``, ``call``,
    ``put``, ``exchange``, ``amount_low``, ``amount_high``, ``first_trade``,
    ``last_trade``, ``issuer_name``, ``sector``, ``return_pct``,
    ``return_trade_count``, ``is_non_equity``.

    The issuer/sector columns are filled best-effort from
    :func:`load_issuer_info_live` so the leaderboard can show a friendly
    name next to each symbol without the frontend doing N+1 lookups.
    The ``return_pct`` column is a notional-weighted average of the per-trade
    market return (price as-of-today vs. price on the trade date) for every
    trade with a Polygon cache hit. ``None`` when the cache has no data.
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
    agg["return_pct"] = None
    agg["return_trade_count"] = 0

    # Build a ticker → asset_name_raw map once, in O(N), instead of doing a
    # full ``sub.loc[sub["ticker"] == t]`` scan for every row of ``agg``.
    if "asset_name_raw" in sub.columns:
        non_empty = sub.loc[sub["asset_name_raw"].fillna("").astype(str).str.strip() != ""]
        if not non_empty.empty:
            asset_name_by_ticker = (
                non_empty.groupby("ticker", observed=True)["asset_name_raw"]
                .first()
                .to_dict()
            )
        else:
            asset_name_by_ticker = {}
    else:
        asset_name_by_ticker = {}
    agg["is_non_equity"] = [
        bool(
            is_non_equity_asset(
                str(t),
                str(asset_name_by_ticker.get(t, "")),
            )
        )
        for t in agg["ticker"]
    ]

    # Issuer/sector metadata: one ``IN (...)`` query per source table, not
    # one query per ticker. The previous loop did ~2000 round-trips and was
    # the dominant cost on the leaderboard.
    ticker_list = [str(t) for t in agg["ticker"]]
    issuer_map = _fetch_issuer_info_bulk(ticker_list)
    agg["issuer_name"] = [issuer_map.get(t, {}).get("issuer_name", "") for t in ticker_list]
    agg["sector"] = [issuer_map.get(t, {}).get("sector", "") for t in ticker_list]

    # Per-trade return metrics: load Polygon bars for every ticker that has
    # trades in one round-trip, then drive ``_metrics_from_bars`` per ticker
    # (still per-ticker, but now the bars come from the in-memory dict).
    bars_by_ticker = _fetch_polygon_bars_bulk(ticker_list)
    sub_indexed = sub.set_index("ticker", drop=False)
    for ticker, pairs in bars_by_ticker.items():
        if not pairs:
            continue
        sub_t = sub_indexed.loc[[ticker]]
        if sub_t.empty:
            continue
        metrics = _metrics_from_bars(sub_t, pairs)
        agg_metric = weighted_aggregate_return(metrics)
        if not agg_metric:
            continue
        mask = agg["ticker"] == ticker
        agg.loc[mask, "return_pct"] = agg_metric["return_pct"]
        agg.loc[mask, "return_trade_count"] = agg_metric["trade_count"]

    return agg.sort_values(["trades", "amount_high"], ascending=[False, False]).reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Process-local cache for the leaderboard (mtime + period key)
# --------------------------------------------------------------------------- #
_leaderboard_cache_lock = Lock()
_leaderboard_cache_key: Optional[tuple[str, str, int]] = None
_leaderboard_cache_value: Optional[pd.DataFrame] = None


def _period_cache_token(lookback: int | None, quarters: list[int] | None) -> str:
    q = ",".join(str(q) for q in sorted(quarters or []))
    return f"lb={lookback}|q={q}"


def ticker_leaderboard_cached(
    frame: pd.DataFrame,
    *,
    lookback: int | None,
    quarters: list[int] | None,
) -> pd.DataFrame:
    """Same as :func:`ticker_leaderboard` but memoised on (db mtime, period).

    The leaderboard is the most expensive endpoint in the API; with ~2000
    distinct tickers the first call still costs a couple of seconds. Tests
    typically re-enter the same slice several times, so a process-local
    cache keyed on the dataset mtime + the period filter is a safe win —
    it never serves a stale result as long as the underlying SQLite/CSV
    files are untouched.
    """
    global _leaderboard_cache_key, _leaderboard_cache_value
    key = (_data_cache_key(), _period_cache_token(lookback, quarters), len(frame))
    with _leaderboard_cache_lock:
        if _leaderboard_cache_key == key and _leaderboard_cache_value is not None:
            return _leaderboard_cache_value
        value = ticker_leaderboard(frame)
        _leaderboard_cache_key = key
        _leaderboard_cache_value = value
        return value


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

    # Per-trade price/return (Polygon cache only — never hit the network from
    # the dashboard request path). Result is a parallel list aligned to
    # ``tx_df`` row order.
    tx_returns = trade_return_metrics(tx_df)
    tx_df = tx_df.reset_index(drop=True).assign(
        price_trade=[m.get("price_trade") for m in tx_returns],
        price_session=[m.get("price_session") for m in tx_returns],
        price_asof=[m.get("price_asof") for m in tx_returns],
        price_asof_session=[m.get("price_asof_session") for m in tx_returns],
        return_pct=[m.get("return_pct") for m in tx_returns],
        est_pnl_usd=[m.get("est_pnl_usd") for m in tx_returns],
        is_non_equity=[bool(m.get("is_non_equity", False)) for m in tx_returns],
    )
    tx_columns = tx_columns + [
        "price_trade", "price_session", "price_asof", "price_asof_session",
        "return_pct", "est_pnl_usd", "is_non_equity",
    ]

    aggregate = weighted_aggregate_return(tx_returns)
    profile_return = aggregate["return_pct"] if aggregate else None
    profile_return_count = aggregate["trade_count"] if aggregate else 0

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
        "return_pct": profile_return,
        "return_trade_count": profile_return_count,
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
