from __future__ import annotations

import pandas as pd
import streamlit as st

from src.dashboard_shared import (
    THEME,
    _build_member_activity_timeline,
    _build_rank_chart,
    _format_currency,
    _render_section_intro,
    get_dashboard_context,
    member_ticker_breakdown,
    normalize_party,
)

ctx = get_dashboard_context()
if not ctx["ready"]:
    st.warning("No data loaded.")
    st.stop()

filtered: pd.DataFrame = ctx["filtered"]  # type: ignore[assignment]

_render_section_intro(
    "Members",
    "Politician profiles & leaderboard",
    "Rank members by activity, then drill into each filer's ticker-level buys, sells, calls, and puts over time.",
)

leaderboard = (
    filtered.groupby("member", as_index=False)
    .agg(
        trades=("member", "size"),
        tickers=("ticker", lambda s: s.astype(str).str.strip().replace("", pd.NA).nunique()),
        estimated_value=("estimated_value", "sum"),
        chamber=("chamber", "first"),
        party=("party", "first"),
        state=("state", "first"),
    )
    .sort_values(["trades", "estimated_value"], ascending=[False, False])
)
if "party" in leaderboard.columns:
    leaderboard["party"] = leaderboard["party"].map(normalize_party)

st.subheader("Leaderboard")
st.dataframe(
    leaderboard,
    hide_index=True,
    width="stretch",
    height=360,
    column_config={
        "estimated_value": st.column_config.NumberColumn("Est. midpoint ($)", format="$%d"),
        "trades": st.column_config.NumberColumn("Trades"),
        "tickers": st.column_config.NumberColumn("Unique tickers"),
    },
)

if leaderboard.empty:
    st.stop()

member_options = leaderboard["member"].astype(str).tolist()
default_member = st.session_state.get("dashboard_selected_member")
if default_member not in member_options:
    default_member = member_options[0]

selected = st.selectbox(
    "Member profile",
    member_options,
    index=member_options.index(default_member),
    key="members_profile_select",
)
st.session_state["dashboard_selected_member"] = selected

profile = filtered.loc[filtered["member"].astype(str) == selected]
if profile.empty:
    st.info("No trades for this member in the current slice.")
    st.stop()

chamber = profile["chamber"].iloc[0] if "chamber" in profile.columns else ""
party = normalize_party(profile["party"].iloc[0]) if "party" in profile.columns else ""
state = profile["state"].iloc[0] if "state" in profile.columns else ""
est = profile["estimated_value"].sum(skipna=True)

cols = st.columns(4)
cols[0].metric("Trades", f"{len(profile):,}")
cols[1].metric("Tickers", f"{profile.loc[profile['ticker'] != '', 'ticker'].nunique():,}")
cols[2].metric("Est. volume", _format_currency(est))
cols[3].metric("Chamber / party", f"{chamber} · {party}" + (f" ({state})" if state else ""))

st.subheader("By ticker: Buy / Sell / Call / Put")
breakdown = member_ticker_breakdown(filtered, selected)
if breakdown.empty:
    st.info("No resolved tickers for this member.")
else:
    st.dataframe(
        breakdown,
        hide_index=True,
        width="stretch",
        height=min(480, 80 + 35 * len(breakdown)),
        column_config={
            "estimated_value": st.column_config.NumberColumn("Est. midpoint ($)", format="$%d"),
            "first_trade": st.column_config.DatetimeColumn("First trade", format="YYYY-MM-DD"),
            "last_trade": st.column_config.DatetimeColumn("Last trade", format="YYYY-MM-DD"),
        },
    )

st.subheader("Activity over time")
timeline = _build_member_activity_timeline(filtered, selected)
if timeline is None:
    st.info("No dated trades with resolved tickers.")
else:
    st.altair_chart(timeline, width="stretch")

st.subheader("Top tickers by trade count")
top = breakdown.head(12) if not breakdown.empty else pd.DataFrame()
if not top.empty:
    st.altair_chart(
        _build_rank_chart(top, "ticker", "Trades", color=THEME["navy"], y_axis_title="Ticker"),
        width="stretch",
    )
