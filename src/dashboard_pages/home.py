from __future__ import annotations

import pandas as pd
import streamlit as st

from src.dashboard_shared import (
    _build_mix_chart,
    _build_rank_chart,
    _build_time_series_chart,
    _build_ticker_3d_figure,
    _build_ticker_member_timeline,
    _build_member_cumulative_notional_chart,
    _copy,
    _render_section_intro,
    _style_dataframe_buy_sell,
    _ticker_timeline_color_key_html,
    get_dashboard_context,
    render_slice_hero_and_kpis,
    transaction_type_display_label,
)

ctx = get_dashboard_context()
if not ctx["ready"]:
    st.warning("No data loaded. Run ingestion first.")
    st.stop()

filtered: pd.DataFrame = ctx["filtered"]  # type: ignore[assignment]
render_slice_hero_and_kpis()

_render_section_intro(
    _copy("overview_kicker"),
    _copy("overview_title"),
    _copy("overview_copy"),
)

monthly_activity = (
    filtered.dropna(subset=["month"])
    .groupby("month", as_index=False)
    .agg(transactions=("member", "size"), estimated_value=("estimated_value", "sum"))
    .sort_values("month")
)
chamber_mix = (
    filtered.groupby("chamber", as_index=False)
    .size()
    .rename(columns={"size": "transactions"})
    .sort_values("transactions", ascending=False)
)
transaction_mix = (
    filtered.groupby("transaction_type_label", as_index=False)
    .size()
    .rename(columns={"size": "transactions"})
    .sort_values("transactions", ascending=False)
)
top_members = (
    filtered.groupby("member", as_index=False)
    .agg(transactions=("member", "size"), estimated_value=("estimated_value", "sum"))
    .sort_values(["transactions", "estimated_value"], ascending=[False, False])
    .head(10)
)
top_tickers = (
    filtered.loc[filtered["ticker"] != ""]
    .groupby("ticker", as_index=False)
    .agg(transactions=("ticker", "size"), estimated_value=("estimated_value", "sum"))
    .sort_values(["transactions", "estimated_value"], ascending=[False, False])
    .head(10)
)

left, right = st.columns([1.4, 1])
with left:
    st.subheader(_copy("sub_monthly_activity"))
    if monthly_activity.empty:
        st.info("No valid transaction dates in the current filter.")
    else:
        st.caption(_copy("chart_caption_monthly"))
        st.altair_chart(_build_time_series_chart(monthly_activity), width="stretch")

    st.subheader(_copy("sub_top_members"))
    if top_members.empty:
        st.info("No member activity for the current filter.")
    else:
        st.caption(_copy("chart_caption_rank_members"))
        st.altair_chart(
            _build_rank_chart(
                top_members,
                "member",
                "Transaction count",
                color="#20344a",
                y_axis_title="Member",
            ),
            width="stretch",
        )
        st.dataframe(
            top_members,
            hide_index=True,
            width="stretch",
            height=320,
            column_config={
                "estimated_value": st.column_config.NumberColumn("Estimated Midpoint", format="$%d"),
            },
        )

with right:
    st.subheader(_copy("sub_chamber_mix"))
    if chamber_mix.empty:
        st.info("No chamber distribution for the current filter.")
    else:
        st.caption(_copy("chart_caption_mix_chamber"))
        st.altair_chart(
            _build_mix_chart(chamber_mix, "chamber", color="#2d6f6d", x_axis_title="Chamber"),
            width="stretch",
        )

    st.subheader(_copy("sub_transaction_type_mix"))
    if transaction_mix.empty:
        st.info("No transaction-type distribution for the current filter.")
    else:
        st.caption(_copy("chart_caption_mix_txn_type"))
        st.altair_chart(
            _build_mix_chart(
                transaction_mix,
                "transaction_type_label",
                color="#a64b2a",
                x_axis_title="Transaction type (display label)",
            ),
            width="stretch",
        )

    st.subheader(_copy("sub_top_tickers"))
    if top_tickers.empty:
        st.info("No resolved tickers in the current filter.")
    else:
        st.caption(_copy("chart_caption_rank_tickers"))
        st.altair_chart(
            _build_rank_chart(
                top_tickers,
                "ticker",
                "Transaction count",
                color="#c6922b",
                y_axis_title="Ticker",
            ),
            width="stretch",
        )
        st.dataframe(
            top_tickers,
            hide_index=True,
            width="stretch",
            height=320,
            column_config={
                "estimated_value": st.column_config.NumberColumn("Estimated Midpoint", format="$%d"),
            },
        )

st.divider()
st.subheader(_copy("sub_latest_transactions"))
latest_transactions = filtered.sort_values(["transaction_date", "filing_date"], ascending=[False, False]).head(50)
_latest_df = latest_transactions[
    [
        "transaction_date",
        "filing_date",
        "filing_type",
        "member",
        "chamber",
        "party",
        "issuer_name",
        "ticker",
        "transaction_type_label",
        "transaction_type",
        "amount_range_raw",
        "confidence_score",
        "review_status",
        "disclosure_url",
    ]
]
st.dataframe(
    _style_dataframe_buy_sell(_latest_df),
    hide_index=True,
    width="stretch",
    height=420,
    column_config={
        "transaction_date": st.column_config.DateColumn("Transaction Date", format="YYYY-MM-DD"),
        "filing_date": st.column_config.DateColumn("Filing Date", format="YYYY-MM-DD"),
        "disclosure_url": st.column_config.LinkColumn("Source PDF (PTR)", display_text="Open PDF"),
    },
)

st.divider()
st.subheader(_copy("overview_detail_heading"))
st.caption(_copy("overview_detail_caption"))
st.subheader(_copy("sub_ticker_who_when"))
st.caption(_copy("ticker_chart_caption"))
tickers_available = sorted(x for x in filtered.loc[filtered["ticker"].astype(str) != "", "ticker"].astype(str).unique() if x)
if not tickers_available:
    st.info("No resolved tickers in the current slice.")
else:
    pick_col, override_col = st.columns([1, 1])
    with pick_col:
        selected_ticker = st.selectbox(
            "Ticker",
            tickers_available,
            label_visibility="collapsed",
            key="home_ticker_timeline_pick",
        )
    with override_col:
        manual = st.text_input(
            "Ticker override (optional)",
            placeholder="e.g. MSFT",
            key="home_ticker_manual",
        ).strip().upper()
    ticker_for_chart = manual if manual else selected_ticker
    ticker_chart = _build_ticker_member_timeline(filtered, ticker_for_chart)
    if ticker_chart is None:
        st.info(f"No transactions for ticker **{ticker_for_chart}** in the current slice.")
    else:
        slice_tick = filtered[filtered["ticker"].astype(str).str.upper().eq(ticker_for_chart)]
        labs = slice_tick["transaction_type"].map(transaction_type_display_label).astype(str).unique().tolist()
        preferred = ["Buy", "Sell", "Sell (partial)", "Exchange", "Unknown"]
        color_key_order = [x for x in preferred if x in labs] + sorted(x for x in labs if x not in preferred)
        st.markdown(_ticker_timeline_color_key_html(color_key_order), unsafe_allow_html=True)
        st.altair_chart(ticker_chart, width="stretch")
        st.subheader(_copy("sub_ticker_3d"))
        st.caption(_copy("ticker_3d_caption"))
        fig_3d = _build_ticker_3d_figure(filtered, ticker_for_chart)
        if fig_3d is None:
            st.warning("Install **plotly** (`pip install plotly`) to use the 3D view.")
        else:
            st.plotly_chart(fig_3d, width="stretch")

    st.subheader(_copy("sub_cumulative_exposure"))
    st.caption(_copy("cumulative_exposure_caption"))
    cum_chart, _cum_members = _build_member_cumulative_notional_chart(filtered, ticker_for_chart)
    if cum_chart is None:
        st.info(f"No dated transactions for ticker **{ticker_for_chart}** in the current slice.")
    else:
        st.caption(_copy("chart_caption_cumulative"))
        st.altair_chart(cum_chart, width="stretch")
