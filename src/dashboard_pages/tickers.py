from __future__ import annotations

import pandas as pd
import streamlit as st

from src.dashboard_shared import (
    THEME,
    _build_member_cumulative_notional_chart,
    _build_ticker_member_timeline,
    _format_currency,
    _render_section_intro,
    _ticker_timeline_color_key_html,
    build_price_overlay_figure,
    get_dashboard_context,
    ticker_member_breakdown,
    transaction_type_display_label,
)

ctx = get_dashboard_context()
if not ctx["ready"]:
    st.warning("No data loaded.")
    st.stop()

filtered: pd.DataFrame = ctx["filtered"]  # type: ignore[assignment]

_render_section_intro(
    "Tickers",
    "Stock-level congressional activity",
    "See which members traded a ticker, how buys and sells cluster, and price action from the Polygon cache.",
)

tickers_available = sorted(
    x for x in filtered.loc[filtered["ticker"].astype(str) != "", "ticker"].astype(str).unique() if x
)
if not tickers_available:
    st.info("No resolved tickers in the current slice.")
    st.stop()

default_ticker = st.session_state.get("dashboard_selected_ticker")
if default_ticker not in tickers_available:
    default_ticker = tickers_available[0]

pick_col, override_col = st.columns([1, 1])
with pick_col:
    selected = st.selectbox(
        "Ticker",
        tickers_available,
        index=tickers_available.index(default_ticker),
        key="tickers_page_select",
    )
with override_col:
    manual = st.text_input("Override symbol", placeholder="e.g. NVDA", key="tickers_page_manual").strip().upper()

ticker = manual if manual else selected
st.session_state["dashboard_selected_ticker"] = ticker

slice_df = filtered[filtered["ticker"].astype(str).str.upper() == ticker.upper()]
if slice_df.empty:
    st.info(f"No trades for **{ticker}** in the current slice.")
    st.stop()

buys = int((slice_df["transaction_type"].astype(str).str.strip() == "P").sum())
sells = int(slice_df["transaction_type"].astype(str).str.strip().str.startswith("S").sum())
cols = st.columns(4)
cols[0].metric("Trades", f"{len(slice_df):,}")
cols[1].metric("Members", f"{slice_df['member'].nunique():,}")
cols[2].metric("Buy / Sell", f"{buys} / {sells}")
cols[3].metric("Est. volume", _format_currency(slice_df["estimated_value"].sum(skipna=True)))

st.subheader("Who traded this ticker")
who = ticker_member_breakdown(filtered, ticker)
if who.empty:
    st.info("No member breakdown available.")
else:
    st.dataframe(
        who,
        hide_index=True,
        width="stretch",
        height=min(480, 80 + 35 * len(who)),
        column_config={
            "estimated_value": st.column_config.NumberColumn("Est. midpoint ($)", format="$%d"),
            "first_trade": st.column_config.DatetimeColumn("First", format="YYYY-MM-DD"),
            "last_trade": st.column_config.DatetimeColumn("Last", format="YYYY-MM-DD"),
        },
    )

st.subheader("Price & trade overlay")
st.caption("Uses `polygon_daily_bar_cache` only — warm via CLI; no live API calls from the dashboard.")
price_fig = build_price_overlay_figure(filtered, ticker)
if price_fig is None:
    st.info("No Polygon bars cached for this ticker. Trade timeline below still works.")
else:
    st.plotly_chart(price_fig, width="stretch")

st.subheader("Member timeline")
ticker_chart = _build_ticker_member_timeline(filtered, ticker)
if ticker_chart is None:
    st.info("No dated transactions for this ticker.")
else:
    labs = slice_df["transaction_type"].map(transaction_type_display_label).astype(str).unique().tolist()
    preferred = ["Buy", "Sell", "Sell (partial)", "Exchange", "Unknown"]
    color_key_order = [x for x in preferred if x in labs] + sorted(x for x in labs if x not in preferred)
    st.markdown(_ticker_timeline_color_key_html(color_key_order), unsafe_allow_html=True)
    st.altair_chart(ticker_chart, width="stretch")

st.subheader("Cumulative exposure by member")
cum_chart, _ = _build_member_cumulative_notional_chart(filtered, ticker)
if cum_chart is None:
    st.info("No cumulative exposure series for this ticker.")
else:
    st.altair_chart(cum_chart, width="stretch")
