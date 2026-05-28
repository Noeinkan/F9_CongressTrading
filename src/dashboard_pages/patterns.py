from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from src.dashboard_shared import (
    THEME,
    _altair_readability,
    _render_section_intro,
    bipartisan_tickers,
    call_put_monthly,
    detect_coordinated_trades,
    get_dashboard_context,
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
    "Surface tickers multiple members trade together, options skew (calls vs puts), volume spikes, and bipartisan interest.",
)

window_days = st.slider("Lookback window (days)", min_value=30, max_value=365, value=90, step=30, key="patterns_window")
min_members = st.slider("Min members for coordination", min_value=2, max_value=8, value=2, key="patterns_min_members")

st.subheader("Coordinated buying / selling")
coordinated = detect_coordinated_trades(filtered, window_days=window_days, min_members=min_members)
if coordinated.empty:
    st.info("No coordinated patterns for the current slice and window.")
else:
    st.dataframe(
        coordinated,
        hide_index=True,
        width="stretch",
        height=min(520, 80 + 35 * len(coordinated)),
        column_config={
            "date_from": st.column_config.DatetimeColumn("From", format="YYYY-MM-DD"),
            "date_to": st.column_config.DatetimeColumn("To", format="YYYY-MM-DD"),
        },
    )

st.subheader("Call vs put trends")
cp = call_put_monthly(filtered)
if cp.empty:
    st.info("No call/put option trades in the current slice.")
else:
    chart = (
        alt.Chart(cp)
        .mark_area(opacity=0.55)
        .encode(
            x=alt.X("month:T", title="Month"),
            y=alt.Y("transactions:Q", title="Option trades", stack="zero"),
            color=alt.Color(
                "option_side:N",
                title="Side",
                scale=alt.Scale(domain=["Call", "Put"], range=["#15803d", "#be123c"]),
            ),
            tooltip=["month:T", "option_side:N", "transactions:Q"],
        )
        .properties(height=300)
    )
    st.altair_chart(_altair_readability(chart), width="stretch")

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
        ratio_chart = (
            alt.Chart(ratio)
            .mark_line(point=True, color=THEME["accent"])
            .encode(
                x=alt.X("month:T", title="Month"),
                y=alt.Y("call_put_ratio:Q", title="Call ÷ Put ratio"),
            )
            .properties(height=220)
        )
        st.caption("Call ÷ Put ratio by month (>1 means more calls than puts).")
        st.altair_chart(_altair_readability(ratio_chart), width="stretch")

ticker_filter = st.text_input("Filter call/put chart by ticker (optional)", key="patterns_cp_ticker").strip().upper()
if ticker_filter:
    cp_t = call_put_monthly(filtered[filtered["ticker"].astype(str).str.upper() == ticker_filter])
    if not cp_t.empty:
        st.altair_chart(
            _altair_readability(
                alt.Chart(cp_t)
                .mark_bar()
                .encode(x="month:T", y="transactions:Q", color="option_side:N")
                .properties(height=240)
            ),
            width="stretch",
        )

st.subheader("Volume anomalies")
anomalies = volume_anomalies(filtered, recent_days=window_days)
if anomalies.empty:
    st.info("No tickers with unusual recent activity vs history.")
else:
    st.dataframe(anomalies, hide_index=True, width="stretch", height=360)

st.subheader("Bipartisan trades")
bipart = bipartisan_tickers(filtered, window_days=window_days)
if bipart.empty:
    st.info("No tickers with both Democrat and Republican trades in the window.")
else:
    st.dataframe(
        bipart,
        hide_index=True,
        width="stretch",
        height=min(480, 80 + 35 * len(bipart)),
        column_config={
            "date_from": st.column_config.DatetimeColumn("From", format="YYYY-MM-DD"),
            "date_to": st.column_config.DatetimeColumn("To", format="YYYY-MM-DD"),
        },
    )
