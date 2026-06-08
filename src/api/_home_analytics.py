"""Home page analytics (net trade, ticker drill-down rows)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ._format import format_currency_compact, format_cumulative_net_label
from ._patterns_analytics import signed_trade_notional
from .repository import transaction_type_display_label


def aggregate_net_trade_amount(
    frame: pd.DataFrame,
    *,
    top_n: int = 20,
    group_field: str = "ticker",
) -> pd.DataFrame | None:
    """Per-ticker net signed notional for the current filter slice."""
    if frame.empty or group_field not in frame.columns:
        return None

    work = frame.copy()
    if group_field == "ticker":
        work = work[work["ticker"].astype(str).str.strip() != ""]
    if work.empty:
        return None

    work["_signed"] = work.apply(signed_trade_notional, axis=1)
    signed = pd.to_numeric(work["_signed"], errors="coerce").fillna(0.0)
    work["_buy"] = signed.clip(lower=0.0)
    work["_sell"] = (-signed).clip(lower=0.0)

    agg_spec: dict[str, tuple[str, str]] = {
        "net_amount": ("_signed", "sum"),
        "buy_amount": ("_buy", "sum"),
        "sell_amount": ("_sell", "sum"),
        "trades": (group_field, "size"),
    }
    if "transaction_date" in work.columns:
        agg_spec["first_trade"] = ("transaction_date", "min")
        agg_spec["last_trade"] = ("transaction_date", "max")

    agg = work.groupby(group_field, as_index=False).agg(**agg_spec)
    agg = agg[agg["net_amount"].abs() > 0]
    if agg.empty:
        return None

    agg = agg.reindex(agg["net_amount"].abs().sort_values(ascending=False).index).head(top_n)
    agg = agg.sort_values("net_amount", ascending=False)

    agg["direction"] = np.where(agg["net_amount"] >= 0, "Net buying", "Net selling")
    agg["net_label"] = agg["net_amount"].map(format_currency_compact)
    agg["buy_label"] = agg["buy_amount"].map(format_currency_compact)
    agg["sell_label"] = agg["sell_amount"].map(format_currency_compact)
    return agg


def tickers_available(frame: pd.DataFrame) -> list[str]:
    if frame.empty or "ticker" not in frame.columns:
        return []
    vals = frame.loc[frame["ticker"].astype(str).str.strip() != "", "ticker"].astype(str).unique()
    return sorted(v for v in vals if v)


def _ticker_slice(frame: pd.DataFrame, ticker: str) -> pd.DataFrame:
    if not ticker or not str(ticker).strip():
        return frame.iloc[0:0]
    t = str(ticker).strip().upper()
    sub = frame[frame["ticker"].astype(str).str.upper() == t].copy()
    return sub.dropna(subset=["transaction_date"]) if "transaction_date" in sub.columns else sub


def ticker_timeline_rows(frame: pd.DataFrame, ticker: str) -> list[dict[str, object]]:
    sub = _ticker_slice(frame, ticker)
    if sub.empty:
        return []
    sub = sub.copy()
    sub["txn_type_label"] = sub["transaction_type"].map(transaction_type_display_label)
    cols = [
        "member",
        "transaction_date",
        "transaction_type",
        "txn_type_label",
        "amount_low",
        "amount_high",
        "amount_range_raw",
        "issuer_name",
        "chamber",
    ]
    if "owner_type" in sub.columns:
        cols.append("owner_type")
    present = [c for c in cols if c in sub.columns]
    out = sub[present].sort_values(["transaction_date", "member"], ascending=[True, True])
    rows: list[dict[str, object]] = []
    for _, row in out.iterrows():
        rec: dict[str, object] = {}
        for col in present:
            val = row[col]
            if col == "transaction_date" and pd.notna(val):
                rec[col] = pd.Timestamp(val).strftime("%Y-%m-%d")
            elif isinstance(val, (np.floating, float)) and pd.isna(val):
                rec[col] = None
            else:
                rec[col] = val if not (isinstance(val, float) and pd.isna(val)) else None
        rows.append(rec)
    return rows


def ticker_3d_rows(frame: pd.DataFrame, ticker: str) -> list[dict[str, object]]:
    sub = _ticker_slice(frame, ticker)
    if sub.empty:
        return []
    sub = sub.copy()
    sub["txn_type_label"] = sub["transaction_type"].map(transaction_type_display_label)
    hi = pd.to_numeric(sub["amount_high"], errors="coerce").fillna(0.0)
    sub["_z"] = np.log10(hi.clip(lower=0.0) + 1.0)
    rows: list[dict[str, object]] = []
    for _, row in sub.sort_values(["transaction_date", "member"]).iterrows():
        rows.append(
            {
                "date": pd.Timestamp(row["transaction_date"]).strftime("%Y-%m-%d"),
                "member": str(row["member"]),
                "amount_high": float(row["amount_high"]) if pd.notna(row["amount_high"]) else None,
                "transaction_type": str(row.get("transaction_type", "")),
                "txn_type_label": str(row["txn_type_label"]),
                "z": float(row["_z"]),
            }
        )
    return rows


def _dedupe_cumulative_trades(sub: pd.DataFrame) -> pd.DataFrame:
    keys = [
        c
        for c in ("member", "transaction_date", "transaction_type", "amount_low", "amount_high", "filing_date")
        if c in sub.columns
    ]
    if not keys:
        return sub
    return sub.drop_duplicates(subset=keys, keep="first")


def ticker_cumulative_rows(frame: pd.DataFrame, ticker: str, *, top_n: int = 16) -> list[dict[str, object]]:
    sub = _ticker_slice(frame, ticker)
    if sub.empty:
        return []

    sub = _dedupe_cumulative_trades(sub)
    sub["_signed"] = sub.apply(signed_trade_notional, axis=1)
    member_counts = sub["member"].value_counts()
    member_order = member_counts.head(top_n).index.tolist()
    sub = sub[sub["member"].isin(member_order)]
    if sub.empty:
        return []

    sub = sub.sort_values(["member", "transaction_date", "filing_date"], ascending=[True, True, True])
    sub["cumulative_net"] = sub.groupby("member", observed=True)["_signed"].cumsum()

    rows: list[dict[str, object]] = []
    for _, row in sub.iterrows():
        cum = float(row["cumulative_net"])
        rows.append(
            {
                "member": str(row["member"]),
                "date": pd.Timestamp(row["transaction_date"]).strftime("%Y-%m-%d"),
                "cumulative_net": cum,
                "cumulative_label": format_cumulative_net_label(cum),
                "txn_type_label": transaction_type_display_label(row.get("transaction_type")),
            }
        )
    return rows


def net_trade_records(agg: pd.DataFrame | None) -> list[dict[str, object]]:
    if agg is None or agg.empty:
        return []
    cols = [
        "ticker",
        "first_trade",
        "last_trade",
        "direction",
        "net_amount",
        "net_label",
        "buy_label",
        "sell_label",
        "trades",
    ]
    present = [c for c in cols if c in agg.columns]
    rows: list[dict[str, object]] = []
    for _, row in agg.iterrows():
        rec: dict[str, object] = {}
        for col in present:
            val = row[col]
            if col in ("first_trade", "last_trade") and pd.notna(val):
                rec[col] = pd.Timestamp(val).strftime("%Y-%m-%d")
            elif col == "net_amount":
                rec[col] = float(val) if pd.notna(val) else 0.0
            elif col == "trades":
                rec[col] = int(val)
            else:
                rec[col] = val if not (isinstance(val, float) and pd.isna(val)) else None
        rows.append(rec)
    return rows
