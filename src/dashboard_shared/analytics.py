from __future__ import annotations

import pandas as pd


def normalize_party(value: object) -> str:
    p = "" if value is None or (isinstance(value, float) and pd.isna(value)) else str(value).strip()
    if not p:
        return "Unknown"
    low = p.lower()
    if low.startswith("d") or "democrat" in low:
        return "Democrat"
    if low.startswith("r") or "republican" in low:
        return "Republican"
    if low.startswith("i") or "independent" in low:
        return "Independent"
    return p


def classify_option_side(row: pd.Series) -> str:
    combined = " ".join(
        str(row.get(col, "") or "")
        for col in ("asset_type", "asset_name_raw", "asset_name_normalized", "issuer_name")
    ).lower()
    if "put" in combined:
        return "Put"
    if "call" in combined:
        return "Call"
    if "option" in combined:
        return "Option"
    return "Stock"


def add_trade_categories(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["option_side"] = out.apply(classify_option_side, axis=1)
    tt = out["transaction_type"].astype(str).str.strip()
    out["is_buy"] = tt.eq("P")
    out["is_sell"] = tt.str.startswith("S")
    out["party_label"] = out["party"].map(normalize_party) if "party" in out.columns else "Unknown"
    return out


def member_ticker_breakdown(frame: pd.DataFrame, member: str) -> pd.DataFrame:
    sub = frame.loc[frame["member"].astype(str) == str(member)].copy()
    if sub.empty:
        return pd.DataFrame()
    sub = add_trade_categories(sub)
    rows: list[dict[str, object]] = []
    for ticker, g in sub.groupby("ticker", observed=True):
        t = str(ticker).strip()
        if not t:
            continue
        rows.append(
            {
                "ticker": t,
                "buy": int(g["is_buy"].sum()),
                "sell": int(g["is_sell"].sum()),
                "call": int((g["option_side"] == "Call").sum()),
                "put": int((g["option_side"] == "Put").sum()),
                "exchange": int((g["transaction_type"].astype(str).str.strip() == "E").sum()),
                "trades": len(g),
                "estimated_value": float(g["estimated_value"].sum(skipna=True)),
                "first_trade": g["transaction_date"].min(),
                "last_trade": g["transaction_date"].max(),
            }
        )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(["trades", "estimated_value"], ascending=[False, False])


def ticker_member_breakdown(frame: pd.DataFrame, ticker: str) -> pd.DataFrame:
    t = str(ticker).strip().upper()
    sub = frame.loc[frame["ticker"].astype(str).str.upper() == t].copy()
    if sub.empty:
        return pd.DataFrame()
    sub = add_trade_categories(sub)
    rows: list[dict[str, object]] = []
    for member, g in sub.groupby("member", observed=True):
        rows.append(
            {
                "member": member,
                "chamber": g["chamber"].iloc[0] if "chamber" in g.columns else "",
                "party": g["party_label"].iloc[0] if "party_label" in g.columns else "",
                "buy": int(g["is_buy"].sum()),
                "sell": int(g["is_sell"].sum()),
                "call": int((g["option_side"] == "Call").sum()),
                "put": int((g["option_side"] == "Put").sum()),
                "exchange": int((g["transaction_type"].astype(str).str.strip() == "E").sum()),
                "trades": len(g),
                "estimated_value": float(g["estimated_value"].sum(skipna=True)),
                "first_trade": g["transaction_date"].min(),
                "last_trade": g["transaction_date"].max(),
            }
        )
    return pd.DataFrame(rows).sort_values(["trades", "estimated_value"], ascending=[False, False])


def detect_coordinated_trades(
    frame: pd.DataFrame,
    *,
    window_days: int = 90,
    min_members: int = 2,
) -> pd.DataFrame:
    sub = frame.dropna(subset=["transaction_date"]).copy()
    sub = add_trade_categories(sub)
    sub = sub[sub["ticker"].astype(str).str.strip() != ""]
    if sub.empty:
        return pd.DataFrame()
    max_date = sub["transaction_date"].max()
    cutoff = max_date - pd.Timedelta(days=window_days)
    recent = sub[sub["transaction_date"] >= cutoff]
    results: list[dict[str, object]] = []
    for ticker, g in recent.groupby("ticker", observed=True):
        buys = g[g["is_buy"]]
        sells = g[g["is_sell"]]
        buy_members = buys["member"].nunique()
        sell_members = sells["member"].nunique()
        if buy_members >= min_members:
            results.append(
                {
                    "ticker": ticker,
                    "pattern": "Coordinated buy",
                    "members": buy_members,
                    "member_names": ", ".join(sorted(buys["member"].astype(str).unique())),
                    "trades": len(buys),
                    "date_from": buys["transaction_date"].min(),
                    "date_to": buys["transaction_date"].max(),
                }
            )
        if sell_members >= min_members:
            results.append(
                {
                    "ticker": ticker,
                    "pattern": "Coordinated sell",
                    "members": sell_members,
                    "member_names": ", ".join(sorted(sells["member"].astype(str).unique())),
                    "trades": len(sells),
                    "date_from": sells["transaction_date"].min(),
                    "date_to": sells["transaction_date"].max(),
                }
            )
    if not results:
        return pd.DataFrame()
    return pd.DataFrame(results).sort_values(["members", "trades"], ascending=[False, False])


def call_put_monthly(frame: pd.DataFrame) -> pd.DataFrame:
    sub = frame.dropna(subset=["transaction_date"]).copy()
    sub = add_trade_categories(sub)
    sub = sub[sub["option_side"].isin(["Call", "Put"])]
    if sub.empty:
        return pd.DataFrame()
    sub["month"] = sub["transaction_date"].dt.to_period("M").dt.to_timestamp()
    agg = (
        sub.groupby(["month", "option_side"], observed=True)
        .size()
        .reset_index(name="transactions")
        .sort_values("month")
    )
    return agg


def volume_anomalies(frame: pd.DataFrame, *, recent_days: int = 90) -> pd.DataFrame:
    sub = frame.dropna(subset=["transaction_date"]).copy()
    sub = sub[sub["ticker"].astype(str).str.strip() != ""]
    if sub.empty:
        return pd.DataFrame()
    max_date = sub["transaction_date"].max()
    recent_cut = max_date - pd.Timedelta(days=recent_days)
    hist = sub[sub["transaction_date"] < recent_cut]
    recent = sub[sub["transaction_date"] >= recent_cut]
    if recent.empty:
        return pd.DataFrame()
    hist_counts = hist.groupby("ticker", observed=True).size()
    recent_counts = recent.groupby("ticker", observed=True).size()
    rows: list[dict[str, object]] = []
    for ticker, recent_n in recent_counts.items():
        hist_n = int(hist_counts.get(ticker, 0))
        hist_months = max(1, (recent_cut - sub["transaction_date"].min()).days / 30.0)
        baseline = hist_n / hist_months if hist_n else 0.0
        recent_rate = recent_n / (recent_days / 30.0)
        ratio = recent_rate / baseline if baseline > 0 else float(recent_n)
        if recent_n >= 3 and (baseline == 0 or ratio >= 2.0):
            rows.append(
                {
                    "ticker": ticker,
                    "recent_trades": int(recent_n),
                    "historical_trades": hist_n,
                    "activity_ratio": round(ratio, 2),
                }
            )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("activity_ratio", ascending=False)


def bipartisan_tickers(frame: pd.DataFrame, *, window_days: int = 90) -> pd.DataFrame:
    sub = frame.dropna(subset=["transaction_date"]).copy()
    sub = add_trade_categories(sub)
    sub = sub[sub["ticker"].astype(str).str.strip() != ""]
    if sub.empty or "party_label" not in sub.columns:
        return pd.DataFrame()
    max_date = sub["transaction_date"].max()
    cutoff = max_date - pd.Timedelta(days=window_days)
    recent = sub[sub["transaction_date"] >= cutoff]
    rows: list[dict[str, object]] = []
    for ticker, g in recent.groupby("ticker", observed=True):
        parties = {p for p in g["party_label"].unique() if p in ("Democrat", "Republican")}
        if len(parties) < 2:
            continue
        rows.append(
            {
                "ticker": ticker,
                "members": g["member"].nunique(),
                "democrat_trades": int((g["party_label"] == "Democrat").sum()),
                "republican_trades": int((g["party_label"] == "Republican").sum()),
                "member_names": ", ".join(sorted(g["member"].astype(str).unique())),
                "date_from": g["transaction_date"].min(),
                "date_to": g["transaction_date"].max(),
            }
        )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("members", ascending=False)

