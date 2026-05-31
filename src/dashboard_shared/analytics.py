from __future__ import annotations

import pandas as pd

from ..utils import normalize_key


def _signed_amount_median(row: pd.Series) -> float:
    low, high = row.get("amount_low"), row.get("amount_high")
    vals = [float(v) for v in (low, high) if pd.notna(v) and float(v) > 0]
    if not vals:
        return 0.0
    return float(pd.Series(vals).median())


def signed_trade_notional(row: pd.Series) -> float:
    med = _signed_amount_median(row)
    if med == 0:
        return 0.0
    tt = str(row.get("transaction_type", "")).strip()
    if tt == "P":
        return med
    if tt == "S" or tt.startswith("S"):
        return -med
    return 0.0


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
                "amount_low_sum": float(g["amount_low"].sum(skipna=True)),
                "amount_high_sum": float(g["amount_high"].sum(skipna=True)),
                "first_trade": g["transaction_date"].min(),
                "last_trade": g["transaction_date"].max(),
            }
        )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(["trades", "amount_high_sum"], ascending=[False, False])


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
                "amount_low_sum": float(g["amount_low"].sum(skipna=True)),
                "amount_high_sum": float(g["amount_high"].sum(skipna=True)),
                "first_trade": g["transaction_date"].min(),
                "last_trade": g["transaction_date"].max(),
            }
        )
    return pd.DataFrame(rows).sort_values(["trades", "amount_high_sum"], ascending=[False, False])


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


def coordinated_pattern_transactions(
    frame: pd.DataFrame,
    *,
    ticker: str,
    pattern: str,
    window_days: int = 90,
) -> pd.DataFrame:
    """Return disclosure rows that match one coordinated buy/sell pattern row."""
    sub = frame.dropna(subset=["transaction_date"]).copy()
    sub = add_trade_categories(sub)
    sub = sub[sub["ticker"].astype(str).str.strip() != ""]
    if sub.empty:
        return pd.DataFrame()
    max_date = sub["transaction_date"].max()
    cutoff = max_date - pd.Timedelta(days=window_days)
    recent = sub[(sub["transaction_date"] >= cutoff) & (sub["ticker"].astype(str) == str(ticker))]
    if pattern == "Coordinated buy":
        out = recent[recent["is_buy"]]
    elif pattern == "Coordinated sell":
        out = recent[recent["is_sell"]]
    else:
        return pd.DataFrame()
    return out.sort_values(["transaction_date", "member"], ascending=[True, True])


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
    hist_months = max(1, (recent_cut - sub["transaction_date"].min()).days / 30.0)
    recent_months = recent_days / 30.0
    rows: list[dict[str, object]] = []
    for ticker, recent_n in recent_counts.items():
        hist_n = int(hist_counts.get(ticker, 0))
        prior_per_month = hist_n / hist_months if hist_n else 0.0
        recent_per_month = recent_n / recent_months
        spike_ratio = recent_per_month / prior_per_month if prior_per_month > 0 else float(recent_n)
        if recent_n >= 3 and (prior_per_month == 0 or spike_ratio >= 2.0):
            rows.append(
                {
                    "ticker": ticker,
                    "recent_disclosures": int(recent_n),
                    "recent_per_month": round(recent_per_month, 2),
                    "prior_per_month": round(prior_per_month, 2),
                    "spike_ratio": round(spike_ratio, 2),
                }
            )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("spike_ratio", ascending=False)


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


def _committee_jurisdiction_sectors(
    committee: str,
    committee_sector_map: dict[str, list[str]],
) -> set[str]:
    sectors = committee_sector_map.get(committee.strip())
    if sectors:
        return set(sectors)
    key = normalize_key(committee)
    for name, values in committee_sector_map.items():
        if normalize_key(name) == key:
            return set(values)
    return set()


def _matching_committees_for_trade(
    sector: str,
    committees: list[str],
    committee_sector_map: dict[str, list[str]],
) -> list[str]:
    sector_value = str(sector or "").strip()
    if not sector_value or not committees:
        return []
    matches: list[str] = []
    for committee in committees:
        if sector_value in _committee_jurisdiction_sectors(committee, committee_sector_map):
            matches.append(committee)
    return matches


def score_committee_relevance(
    frame: pd.DataFrame,
    committee_assignments: dict[str, list[str]],
    committee_sector_map: dict[str, list[str]],
) -> pd.DataFrame:
    """Score each trade for committee-sector overlap (enterprising-trade signal)."""
    if frame.empty or not committee_assignments:
        return pd.DataFrame()
    sub = frame.copy()
    if "sector" not in sub.columns:
        sub["sector"] = ""
    rows: list[dict[str, object]] = []
    for _, row in sub.iterrows():
        member = str(row.get("member") or "").strip()
        member_key = normalize_key(member)
        committees = committee_assignments.get(member_key, [])
        sector = str(row.get("sector") or "").strip()
        matching = _matching_committees_for_trade(sector, committees, committee_sector_map)
        rows.append(
            {
                "member": member,
                "chamber": row.get("chamber", ""),
                "party": row.get("party", ""),
                "ticker": row.get("ticker", ""),
                "sector": sector,
                "industry": row.get("industry", ""),
                "committees": ", ".join(committees),
                "matching_committees": ", ".join(matching),
                "overlap_score": 1 if matching else 0,
                "transaction_date": row.get("transaction_date"),
                "transaction_type": row.get("transaction_type", ""),
                "transaction_type_label": row.get("transaction_type_label", ""),
                "amount_range_raw": row.get("amount_range_raw", ""),
                "issuer_name": row.get("issuer_name", ""),
                "asset_name_raw": row.get("asset_name_raw", ""),
                "filing_date": row.get("filing_date"),
            }
        )
    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows)
    if "transaction_date" in out.columns:
        out = out.sort_values(["overlap_score", "transaction_date"], ascending=[False, False])
    else:
        out = out.sort_values("overlap_score", ascending=False)
    return out


def summarize_committee_relevance(scored: pd.DataFrame) -> pd.DataFrame:
    """Aggregate committee overlap stats per member."""
    if scored.empty:
        return pd.DataFrame()
    rows: list[dict[str, object]] = []
    for member, g in scored.groupby("member", observed=True):
        total = len(g)
        relevant = int((g["overlap_score"] > 0).sum())
        rel_pct = round(100.0 * relevant / total, 1) if total else 0.0
        rel_rows = g[g["overlap_score"] > 0]
        top_committee = ""
        top_sector = ""
        if not rel_rows.empty and "matching_committees" in rel_rows.columns:
            committee_counts: dict[str, int] = {}
            sector_counts: dict[str, int] = {}
            for _, r in rel_rows.iterrows():
                for c in str(r.get("matching_committees") or "").split(","):
                    c = c.strip()
                    if c:
                        committee_counts[c] = committee_counts.get(c, 0) + 1
                s = str(r.get("sector") or "").strip()
                if s:
                    sector_counts[s] = sector_counts.get(s, 0) + 1
            if committee_counts:
                top_committee = max(committee_counts, key=committee_counts.get)
            if sector_counts:
                top_sector = max(sector_counts, key=sector_counts.get)
        rows.append(
            {
                "member": member,
                "chamber": g["chamber"].iloc[0] if "chamber" in g.columns else "",
                "party": g["party"].iloc[0] if "party" in g.columns else "",
                "total_trades": total,
                "relevant_trades": relevant,
                "relevance_pct": rel_pct,
                "top_committee": top_committee,
                "top_sector": top_sector,
            }
        )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(
        ["relevant_trades", "relevance_pct", "total_trades"],
        ascending=[False, False, False],
    )


def committee_relevant_trades(scored: pd.DataFrame) -> pd.DataFrame:
    """Return only trades with committee-sector overlap."""
    if scored.empty:
        return pd.DataFrame()
    return scored.loc[scored["overlap_score"] > 0].copy()


def member_committee_relevant_transactions(
    frame: pd.DataFrame,
    member: str,
    committee_assignments: dict[str, list[str]],
    committee_sector_map: dict[str, list[str]],
) -> pd.DataFrame:
    """Full transaction rows for one member's committee-relevant trades in the slice."""
    member_name = str(member).strip()
    if frame.empty or not member_name or not committee_assignments:
        return pd.DataFrame()
    member_frame = frame.loc[frame["member"].astype(str) == member_name]
    if member_frame.empty:
        return pd.DataFrame()
    scored = score_committee_relevance(member_frame, committee_assignments, committee_sector_map)
    relevant = committee_relevant_trades(scored)
    if relevant.empty:
        return pd.DataFrame()
    merge_keys = ["member", "ticker", "transaction_date"]
    overlap_cols = [c for c in ("matching_committees",) if c in relevant.columns]
    return member_frame.merge(
        relevant[merge_keys + overlap_cols],
        on=merge_keys,
        how="inner",
        suffixes=("", "_overlap"),
    )


def committee_relevance_coverage(frame: pd.DataFrame, committee_assignments: dict[str, list[str]]) -> dict[str, float]:
    """Coverage stats for the committee relevance card."""
    if frame.empty:
        return {"member_coverage_pct": 0.0, "sector_coverage_pct": 0.0, "members_mapped": 0}
    members = frame["member"].astype(str).unique()
    mapped = sum(1 for m in members if normalize_key(m) in committee_assignments)
    member_cov = round(100.0 * mapped / len(members), 1) if len(members) else 0.0
    if "sector" in frame.columns:
        with_sector = frame["sector"].fillna("").astype(str).str.strip().ne("").sum()
        sector_cov = round(100.0 * with_sector / len(frame), 1) if len(frame) else 0.0
    else:
        sector_cov = 0.0
    return {
        "member_coverage_pct": member_cov,
        "sector_coverage_pct": sector_cov,
        "members_mapped": mapped,
    }

