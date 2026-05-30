from __future__ import annotations



import pandas as pd

import streamlit as st



from src.dashboard_shared import (
    KpiSpec,
    THEME,

    _build_member_activity_timeline,

    _build_rank_chart,

    _render_section_intro,

    _ticker_timeline_color_key_html,

    add_disclosed_range_column,
    format_disclosed_range,
    sum_amount_high,
    sum_amount_low,

    chart_card,

    format_currency_compact,

    format_count,

    get_dashboard_context,

    member_ticker_breakdown,

    monthly_series,

    normalize_party,

    render_kpi_row,
    render_summary_table,

    transaction_type_display_label,

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

        amount_low=("amount_low", "sum"),
        amount_high=("amount_high", "sum"),

        chamber=("chamber", "first"),

        party=("party", "first"),

        state=("state", "first"),

    )

    .sort_values(["trades", "amount_high"], ascending=[False, False])

)

if "party" in leaderboard.columns:

    leaderboard["party"] = leaderboard["party"].map(normalize_party)



with chart_card("Leaderboard"):
    render_summary_table(
        add_disclosed_range_column(leaderboard, low_col="amount_low", high_col="amount_high")[
            ["member", "trades", "tickers", "disclosed_range", "chamber", "party", "state"]
        ],
        headers={
            "member": "Member",
            "trades": "Trades",
            "tickers": "Unique tickers",
            "disclosed_range": "Disclosed range",
            "chamber": "Chamber",
            "party": "Party",
            "state": "State",
        },
    )



if leaderboard.empty:

    st.stop()



member_options = leaderboard["member"].astype(str).tolist()

qp_member = st.query_params.get("member")
if qp_member and qp_member in member_options:
    default_member = qp_member
    st.query_params.pop("member", None)
else:
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

amount_low_total = sum_amount_low(profile)
amount_high_total = sum_amount_high(profile)

chamber_party = f"{chamber} · {party}" + (f" ({state})" if state else "")



render_kpi_row(

    [

        KpiSpec(

            "Trades",

            format_count(len(profile)),

            "Disclosures in the active slice",

            sparkline=monthly_series(profile, "transactions") or None,

        ),

        KpiSpec(

            "Tickers",

            format_count(profile.loc[profile["ticker"] != "", "ticker"].nunique()),

            "Resolved symbols",

            sparkline=monthly_series(profile, "tickers") or None,

        ),

        KpiSpec(

            "Disclosed range",

            format_disclosed_range(amount_low_total, amount_high_total),

            "Sum of amount_low – sum of amount_high for this member",

            sparkline=monthly_series(profile, "disclosed_amount_high") or None,

            delta_percent=True,

        ),

        ("Chamber / party", chamber_party or "—", "From member metadata"),

    ]

)



with chart_card(

    "By ticker",

    caption="Buy, sell, call, and put counts per resolved ticker for the selected member.",

):

    breakdown = member_ticker_breakdown(filtered, selected)

    if breakdown.empty:

        st.info("No resolved tickers for this member.")

    else:

        _bd = breakdown.copy()

        _bd = add_disclosed_range_column(_bd, low_col="amount_low_sum", high_col="amount_high_sum")

        render_summary_table(
            _bd,
            headers={
                "ticker": "Ticker",
                "buy": "Buys",
                "sell": "Sells",
                "call": "Calls",
                "put": "Puts",
                "trades": "Trades",
                "disclosed_range": "Disclosed range",
                "first_trade": "First trade",
                "last_trade": "Last trade",
            },
        )



with chart_card(

    "Activity over time",

    caption=(

        "Each dot is one disclosure. Rows are tickers (newest activity at top); "

        "the x-axis is transaction date."

    ),

):

    timeline, truncate_note = _build_member_activity_timeline(filtered, selected)

    if timeline is None:

        st.info("No dated trades with resolved tickers.")

    else:

        if truncate_note:

            st.caption(truncate_note)

        _profile_tickers = profile.loc[profile["ticker"].astype(str).str.strip() != ""]

        _type_labels = _profile_tickers["transaction_type"].map(transaction_type_display_label).astype(str).unique().tolist()

        _preferred = ["Buy", "Sell", "Sell (partial)", "Exchange", "Unknown"]

        _color_key_order = [x for x in _preferred if x in _type_labels] + sorted(

            x for x in _type_labels if x not in _preferred

        )

        st.markdown(_ticker_timeline_color_key_html(_color_key_order), unsafe_allow_html=True)

        st.altair_chart(timeline, width="stretch")



with chart_card("Top tickers by trade count"):

    breakdown = member_ticker_breakdown(filtered, selected)

    top = breakdown.head(12).rename(columns={"trades": "transactions"}) if not breakdown.empty else pd.DataFrame()

    if top.empty:

        st.info("No ticker ranking for this member.")

    else:

        st.altair_chart(

            _build_rank_chart(top, "ticker", "Trades", color=THEME["chart_series_primary"], y_axis_title="Ticker"),

            width="stretch",

        )

