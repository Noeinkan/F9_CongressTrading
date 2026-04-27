from __future__ import annotations

import os
import sqlite3
from datetime import date, datetime, timedelta, time
from typing import Any, Mapping, Sequence
from urllib.parse import quote, urljoin
from zoneinfo import ZoneInfo

from .config import POLYGON_AGGS_DAY, USER_AGENT
from .ticker_lookup import POLYGON_LIMITER, _request_with_rate_limit

_ET = ZoneInfo("America/New_York")


def _date_to_et_midnight_ms(d: date) -> int:
    dt = datetime.combine(d, time.min, tzinfo=_ET)
    return int(dt.timestamp() * 1000)


def _parse_polygon_bar_date_ms(ms: int) -> date:
    return datetime.fromtimestamp(ms / 1000.0, tz=_ET).date()


def _normalize_ticker_path(ticker: str) -> str:
    t = (ticker or "").strip().upper()
    return t


def resolve_session_close(bars: Sequence[tuple[date, float]], target: date) -> tuple[float, date] | None:
    """Same calendar session, else first session after target, else last session before."""
    if not bars:
        return None
    dates_closes = sorted(bars, key=lambda x: x[0])
    for d, c in dates_closes:
        if d == target:
            return (c, d)
    after = [(d, c) for d, c in dates_closes if d > target]
    if after:
        d0, c0 = after[0]
        return (c0, d0)
    before = [(d, c) for d, c in dates_closes if d < target]
    if before:
        d0, c0 = before[-1]
        return (c0, d0)
    return None


def _median_amount(low: Any, high: Any) -> float | None:
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


def _signed_return_and_pnl(
    transaction_type: str,
    price_trade: float,
    price_asof: float,
    median_notional: float | None,
) -> tuple[float | None, float | None]:
    if price_trade <= 0 or price_asof <= 0:
        return None, None
    mkt_ret = price_asof / price_trade - 1.0
    ret_pct = mkt_ret * 100.0
    tt = (transaction_type or "").strip()
    if median_notional is None or median_notional <= 0:
        return ret_pct, None
    if tt == "P":
        return ret_pct, median_notional * mkt_ret
    if tt == "S" or tt.startswith("S"):
        return ret_pct, -median_notional * mkt_ret
    return ret_pct, None


def _cache_range_for_ticker(conn: sqlite3.Connection, ticker: str) -> tuple[str | None, str | None]:
    row = conn.execute(
        "SELECT MIN(bar_date), MAX(bar_date) FROM polygon_daily_bar_cache WHERE ticker = ?",
        (ticker,),
    ).fetchone()
    if row is None or row[0] is None:
        return None, None
    return str(row[0]), str(row[1])


def _cache_covers(conn: sqlite3.Connection, ticker: str, d_lo: date, d_hi: date) -> bool:
    mn, mx = _cache_range_for_ticker(conn, ticker)
    if not mn or not mx:
        return False
    return mn <= d_lo.isoformat() and mx >= d_hi.isoformat()


def _load_bars(conn: sqlite3.Connection, ticker: str, d_lo: date, d_hi: date) -> list[tuple[date, float]]:
    rows = conn.execute(
        """
        SELECT bar_date, close FROM polygon_daily_bar_cache
        WHERE ticker = ? AND bar_date >= ? AND bar_date <= ?
        ORDER BY bar_date
        """,
        (ticker, d_lo.isoformat(), d_hi.isoformat()),
    ).fetchall()
    out: list[tuple[date, float]] = []
    for r in rows:
        try:
            d = date.fromisoformat(str(r["bar_date"]))
        except ValueError:
            continue
        out.append((d, float(r["close"])))
    return out


def _upsert_bars(conn: sqlite3.Connection, ticker: str, bars: Sequence[tuple[date, float]]) -> None:
    if not bars:
        return
    conn.executemany(
        """
        INSERT INTO polygon_daily_bar_cache (ticker, bar_date, close)
        VALUES (?, ?, ?)
        ON CONFLICT(ticker, bar_date) DO UPDATE SET
            close = excluded.close,
            fetched_at = datetime('now')
        """,
        [(ticker, d.isoformat(), c) for d, c in bars],
    )
    conn.commit()


def fetch_polygon_daily_bars(
    ticker: str,
    d_lo: date,
    d_hi: date,
    api_key: str,
) -> list[tuple[date, float]]:
    """One or more GETs; returns sorted (session_date, adjusted close)."""
    t = _normalize_ticker_path(ticker)
    if not t:
        return []
    from_ms = _date_to_et_midnight_ms(d_lo)
    to_ms = _date_to_et_midnight_ms(d_hi + timedelta(days=1)) - 1
    headers = {"User-Agent": USER_AGENT}
    bars: list[tuple[date, float]] = []
    path_url = POLYGON_AGGS_DAY.format(ticker=quote(t, safe=""), from_ms=from_ms, to_ms=to_ms)
    url: str | None = (
        f"{path_url}?adjusted=true&sort=asc&limit=50000&apiKey={quote(api_key, safe='')}"
    )
    while url:
        resp = _request_with_rate_limit(
            "GET",
            url,
            limiter=POLYGON_LIMITER,
            headers=headers,
            timeout=60,
        )
        if resp is None:
            break
        try:
            data = resp.json()
        except ValueError:
            break
        status = (data.get("status") or "").upper()
        if status and status not in {"OK", "DELAYED"}:
            break
        for item in data.get("results") or []:
            try:
                ms = int(item["t"])
                c = float(item["c"])
            except (KeyError, TypeError, ValueError):
                continue
            bars.append((_parse_polygon_bar_date_ms(ms), c))
        nxt = data.get("next_url")
        if not nxt or not isinstance(nxt, str):
            break
        if nxt.startswith("http://") or nxt.startswith("https://"):
            url = nxt
        else:
            url = urljoin("https://api.polygon.io", nxt)
        if "apiKey=" not in url and "apikey=" not in url.lower():
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}apiKey={quote(api_key, safe='')}"
    bars.sort(key=lambda x: x[0])
    dedup: dict[date, float] = {}
    for d0, c0 in bars:
        dedup[d0] = c0
    return sorted(dedup.items(), key=lambda x: x[0])


def ensure_bars_for_ticker(
    conn: sqlite3.Connection,
    ticker: str,
    d_lo: date,
    d_hi: date,
    api_key: str,
    *,
    force_refetch: bool,
    cache_only: bool,
) -> list[tuple[date, float]]:
    t = _normalize_ticker_path(ticker)
    if not t:
        return []
    pad_lo = d_lo - timedelta(days=21)
    pad_hi = d_hi + timedelta(days=21)
    if not force_refetch and _cache_covers(conn, t, pad_lo, pad_hi):
        return _load_bars(conn, t, pad_lo, pad_hi)
    if cache_only:
        return _load_bars(conn, t, pad_lo, pad_hi)
    fetched = fetch_polygon_daily_bars(t, pad_lo, pad_hi, api_key)
    _upsert_bars(conn, t, fetched)
    return _load_bars(conn, t, pad_lo, pad_hi)


def warm_polygon_price_cache_for_db(
    conn: sqlite3.Connection,
    *,
    as_of: date,
    api_key: str | None = None,
    force_refetch: bool = False,
    cache_only: bool = False,
) -> int:
    """
    Prefetch Polygon daily bars for every distinct ticker with a parseable transaction_date
    in `transactions`. Returns count of tickers requested (network or cache-only).
    """
    key = api_key or os.getenv("POLYGON_API_KEY", "").strip()
    if not key and not cache_only:
        raise RuntimeError("POLYGON_API_KEY mancante")
    rows = conn.execute(
        """
        SELECT DISTINCT UPPER(TRIM(ticker)) AS ticker, MIN(t.transaction_date) AS mn, MAX(t.transaction_date) AS mx
        FROM transactions t
        WHERE TRIM(ticker) <> ''
          AND LENGTH(TRIM(t.transaction_date)) >= 10
        GROUP BY UPPER(TRIM(ticker))
        """
    ).fetchall()
    n = 0
    for row in rows:
        tk = str(row["ticker"] or "").strip()
        if not tk:
            continue
        try:
            d_min = date.fromisoformat(str(row["mn"]).strip()[:10])
            d_max = date.fromisoformat(str(row["mx"]).strip()[:10])
        except ValueError:
            continue
        lo = min(d_min, as_of)
        hi = max(d_max, as_of)
        ensure_bars_for_ticker(conn, tk, lo, hi, key or "", force_refetch=force_refetch, cache_only=cache_only)
        n += 1
    return n


def _parse_txn_date(raw: Any) -> date | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if len(s) < 10:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def enrich_export_rows_with_polygon_pnl(
    conn: sqlite3.Connection,
    rows: Sequence[Mapping[str, Any]],
    *,
    as_of: date,
    api_key: str,
    force_refetch: bool,
    cache_only: bool,
) -> list[dict[str, Any]]:
    """
    For each export row (sqlite Row-like), attach Polygon-based fields.
    Mutates nothing on `rows`; returns parallel list of flat dicts with extra keys.
    """
    by_ticker: dict[str, list[date]] = {}
    for row in rows:
        tk = _normalize_ticker_path(str(row["ticker"] or ""))
        td = _parse_txn_date(row["transaction_date"])
        if not tk or td is None:
            continue
        by_ticker.setdefault(tk, []).append(td)
    as_of_clamped = as_of
    bar_book: dict[str, list[tuple[date, float]]] = {}
    for tk, dates in by_ticker.items():
        d_lo = min(min(dates), as_of_clamped)
        d_hi = max(max(dates), as_of_clamped)
        bar_book[tk] = ensure_bars_for_ticker(
            conn,
            tk,
            d_lo,
            d_hi,
            api_key,
            force_refetch=force_refetch,
            cache_only=cache_only,
        )

    out: list[dict[str, Any]] = []
    for row in rows:
        base = dict(row)
        tk = _normalize_ticker_path(str(row["ticker"] or ""))
        td = _parse_txn_date(row["transaction_date"])
        med = _median_amount(row["amount_low"], row["amount_high"])
        tt = str(row["transaction_type"] or "").strip()

        base["polygon_price_session"] = ""
        base["polygon_price_trade"] = ""
        base["polygon_price_asof_session"] = ""
        base["polygon_price_asof"] = ""
        base["polygon_mkt_return_pct"] = ""
        base["polygon_signed_est_pnl_usd"] = ""

        if not tk or td is None:
            out.append(base)
            continue
        bars = bar_book.get(tk) or []
        hit_trade = resolve_session_close(bars, td)
        hit_asof = resolve_session_close(bars, as_of_clamped)
        if hit_trade is None or hit_asof is None:
            out.append(base)
            continue
        pt, session_trade = hit_trade
        pa, session_asof = hit_asof
        ret_pct, pnl = _signed_return_and_pnl(tt, pt, pa, med)
        base["polygon_price_session"] = session_trade.isoformat()
        base["polygon_price_trade"] = f"{pt:.6g}"
        base["polygon_price_asof_session"] = session_asof.isoformat()
        base["polygon_price_asof"] = f"{pa:.6g}"
        if ret_pct is not None:
            base["polygon_mkt_return_pct"] = f"{ret_pct:.6g}"
        if pnl is not None:
            base["polygon_signed_est_pnl_usd"] = f"{pnl:.6g}"
        out.append(base)
    return out


POLYGON_PNL_EXTRA_COLUMNS = [
    "polygon_price_session",
    "polygon_price_trade",
    "polygon_price_asof_session",
    "polygon_price_asof",
    "polygon_mkt_return_pct",
    "polygon_signed_est_pnl_usd",
]
