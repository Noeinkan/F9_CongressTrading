from __future__ import annotations



import pandas as pd

import streamlit as st



from src.dashboard_shared import (
    COMMITTEE_SECTOR_MAP,
    KpiSpec,
    MEMBERS_VIEW_COMMITTEE_RELEVANCE,
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


    load_committee_assignments_live,

    member_committee_relevant_transactions,

    member_ticker_breakdown,

    monthly_series,

    normalize_party,

    render_kpi_row,
    render_summary_table,
    render_transaction_table,

    transaction_type_display_label,

)


def render(ctx: dict[str, object]) -> None:
    """Dashboard page — called from dashboard.py dispatch."""
    if not ctx["ready"]:
        st.warning("No data loaded.")
        return



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



    if leaderboard.empty:

        st.stop()



    member_options = leaderboard["member"].astype(str).tolist()

    qp_member = st.query_params.get("member")
    if qp_member and qp_member in member_options:
        st.session_state["dashboard_selected_member"] = qp_member
        st.session_state["members_profile_select"] = qp_member
        st.query_params.pop("member", None)

    qp_view = st.query_params.get("view")
    if qp_view == MEMBERS_VIEW_COMMITTEE_RELEVANCE:
        st.session_state["members_trade_view"] = MEMBERS_VIEW_COMMITTEE_RELEVANCE
        st.query_params.pop("view", None)

    _lb_display = add_disclosed_range_column(leaderboard, low_col="amount_low", high_col="amount_high")[
        ["member", "trades", "tickers", "disclosed_range", "chamber", "party", "state"]
    ].rename(columns={
        "member": "Member",
        "trades": "Trades",
        "tickers": "Unique tickers",
        "disclosed_range": "Disclosed range",
        "chamber": "Chamber",
        "party": "Party",
        "state": "State",
    }).reset_index(drop=True)

    with chart_card("Leaderboard", caption="Click a row to view that member's profile below."):
        event = st.dataframe(
            _lb_display,
            on_select="rerun",
            selection_mode="single-row",
            hide_index=True,
            use_container_width=True,
        )
        if event.selection.rows:
            _clicked = member_options[event.selection.rows[0]]
            if _clicked != st.session_state.get("dashboard_selected_member"):
                st.session_state["dashboard_selected_member"] = _clicked
                st.session_state["members_profile_select"] = _clicked
                st.rerun()

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

    committee_assignments = load_committee_assignments_live()
    trade_view_options = {
        "All trades": "all",
        "Committee relevant": MEMBERS_VIEW_COMMITTEE_RELEVANCE,
    }
    _default_trade_view = st.session_state.get("members_trade_view", "all")
    if _default_trade_view not in trade_view_options.values():
        _default_trade_view = "all"
    _trade_view_label = next(
        (label for label, value in trade_view_options.items() if value == _default_trade_view),
        "All trades",
    )
    trade_view = st.pills(
        "Transaction view",
        list(trade_view_options.keys()),
        default=_trade_view_label,
        key="members_trade_view_pills",
    )
    st.session_state["members_trade_view"] = trade_view_options.get(str(trade_view), "all")

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

    if st.session_state.get("members_trade_view") == MEMBERS_VIEW_COMMITTEE_RELEVANCE:
        with chart_card(
            "Committee-relevant trades",
            caption=(
                "Disclosures where this member's committee jurisdiction overlaps the traded company's sector. "
                "Linked from Patterns → Committee relevance."
            ),
        ):
            if not committee_assignments:
                st.info("No committee assignments in data/committees.json.")
            else:
                committee_tx = member_committee_relevant_transactions(
                    filtered,
                    selected,
                    committee_assignments,
                    COMMITTEE_SECTOR_MAP,
                )
                if committee_tx.empty:
                    st.info("No committee-relevant trades for this member in the current slice.")
                else:
                    if "matching_committees" in committee_tx.columns:
                        render_summary_table(
                            committee_tx,
                            columns=[
                                "ticker",
                                "sector",
                                "matching_committees",
                                "transaction_type_label",
                                "transaction_date",
                                "amount_range_raw",
                            ],
                            headers={
                                "ticker": "Ticker",
                                "sector": "Sector",
                                "matching_committees": "Committee overlap",
                                "transaction_type_label": "Transaction",
                                "transaction_date": "Traded",
                                "amount_range_raw": "Amount",
                            },
                            link_columns={
                                "ticker": {"page": "Tickers", "query": {"ticker": "ticker"}},
                            },
                        )
                    render_transaction_table(
                        committee_tx,
                        limit=100,
                        with_polygon=True,
                        show_return_legend=True,
                        widget_key="members_committee_txn",
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

        _rank = _build_rank_chart(top, "ticker", "Trades", color=THEME["chart_series_primary"], y_axis_title="Ticker") if not top.empty else None

        if _rank is None:

            st.info("No ticker ranking for this member.")

        else:

            st.altair_chart(_rank, width="stretch")

