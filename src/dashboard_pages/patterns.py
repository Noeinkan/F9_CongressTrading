from __future__ import annotations



import pandas as pd

import streamlit as st



from src.dashboard_shared import (
    _build_call_put_ratio_chart,
    _build_option_side_area_chart,
    _render_section_intro,
    bipartisan_tickers,
    call_put_monthly,
    chart_card,
    coordinated_pattern_transactions,
    detect_coordinated_trades,
    get_dashboard_context,
    render_summary_table,
    render_transaction_table,
    volume_anomalies,
)



ctx = get_dashboard_context()

if not ctx["ready"]:

    st.warning("No data loaded.")

    st.stop()



filtered: pd.DataFrame = ctx["filtered"]  # type: ignore[assignment]



_render_section_intro(

    "Patterns",

    "Signals & coordination",

    "Surface tickers multiple members trade together, options skew (calls vs puts), disclosure spikes, and bipartisan interest.",

)



window_days = st.slider("Lookback window (days)", min_value=30, max_value=365, value=90, step=30, key="patterns_window")

min_members = st.slider("Min members for coordination", min_value=2, max_value=8, value=2, key="patterns_min_members")



with chart_card("Coordinated buying / selling"):

    coordinated = detect_coordinated_trades(filtered, window_days=window_days, min_members=min_members)

    if coordinated.empty:

        st.info("No coordinated patterns for the current slice and window.")

    else:
        st.caption("Pick a pattern below to expand matching transactions.")
        render_summary_table(
            coordinated,
            headers={
                "ticker": "Ticker",
                "pattern": "Pattern",
                "members": "Members",
                "member_names": "Member names",
                "trades": "Trades",
                "date_from": "From",
                "date_to": "To",
            },
        )
        pattern_labels = [
            f"{row['ticker']} · {row['pattern']} · {int(row['members'])} members"
            for _, row in coordinated.iterrows()
        ]
        pick = st.selectbox(
            "Coordinated pattern",
            pattern_labels,
            key="patterns_coordinated_pick",
        )
        row = coordinated.iloc[pattern_labels.index(pick)]
        pattern_tx = coordinated_pattern_transactions(
            filtered,
            ticker=str(row["ticker"]),
            pattern=str(row["pattern"]),
            window_days=window_days,
        )
        st.markdown(f"**Transactions · {row['ticker']} · {row['pattern']}**")
        render_transaction_table(pattern_tx, limit=50, with_polygon=False, show_return_legend=False)



with chart_card(

    "Call vs put trends",

    caption="Stacked monthly option disclosures; ratio chart compares call volume to put volume.",

):

    cp = call_put_monthly(filtered)

    if cp.empty:

        st.info("No call/put option trades in the current slice.")

    else:

        st.altair_chart(_build_option_side_area_chart(cp), width="stretch")



        ratio = (

            cp.pivot(index="month", columns="option_side", values="transactions")

            .fillna(0)

            .reset_index()

        )

        if "Call" in ratio.columns and "Put" in ratio.columns:

            ratio["call_put_ratio"] = ratio.apply(

                lambda r: (r["Call"] / r["Put"]) if r["Put"] > 0 else float(r["Call"]),

                axis=1,

            )

            st.caption("Values above 1 mean more calls than puts that month.")

            st.altair_chart(_build_call_put_ratio_chart(ratio), width="stretch")



ticker_filter = st.text_input("Filter call/put chart by ticker (optional)", key="patterns_cp_ticker").strip().upper()

if ticker_filter:

    cp_t = call_put_monthly(filtered[filtered["ticker"].astype(str).str.upper() == ticker_filter])

    if not cp_t.empty:

        with chart_card(f"Call vs put · {ticker_filter}"):

            st.altair_chart(_build_option_side_area_chart(cp_t), width="stretch")



with chart_card(
    "Disclosure spikes",
    caption=(
        f"Tickers where members filed unusually often in the last {window_days} days compared with "
        f"their long-run pace. Counts are PTR disclosure rows, not stock-market volume. "
        f"Listed when there are ≥3 recent disclosures and the recent monthly rate is ≥2× the prior rate."
    ),
):

    anomalies = volume_anomalies(filtered, recent_days=window_days)

    if anomalies.empty:

        st.info("No tickers with unusually heavy recent disclosure activity vs prior history.")

    else:

        render_summary_table(
            anomalies,
            headers={
                "ticker": "Ticker",
                "recent_disclosures": "Recent disclosures",
                "recent_per_month": "Recent / mo",
                "prior_per_month": "Prior / mo",
                "spike_ratio": "Spike ratio",
            },
        )



with chart_card("Bipartisan trades"):

    bipart = bipartisan_tickers(filtered, window_days=window_days)

    if bipart.empty:

        st.info("No tickers with both Democrat and Republican trades in the window.")

    else:

        render_summary_table(
            bipart,
            headers={
                "ticker": "Ticker",
                "members": "Members",
                "democrat_trades": "Dem trades",
                "republican_trades": "Rep trades",
                "member_names": "Member names",
                "date_from": "From",
                "date_to": "To",
            },
        )

