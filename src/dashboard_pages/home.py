from __future__ import annotations

import pandas as pd
import streamlit as st

from src.dashboard_shared import (
    _aggregate_net_trade_amount,
    _build_net_trade_amount_chart,
    _build_rank_chart,
    _build_time_series_chart,
    _build_ticker_3d_figure,
    _build_ticker_member_timeline,
    _build_member_cumulative_notional_chart,
    _copy,
    _cumulative_exposure_guide_html,
    _render_section_intro,
    _ticker_timeline_color_key_html,
    add_disclosed_range_column,
    chart_card,
    render_summary_table,
    render_transaction_table,
    render_slice_hero_and_kpis,
    transaction_type_display_label,
    THEME,
)


def render(ctx: dict[str, object]) -> None:
    """Dashboard page — called from dashboard.py dispatch."""
    if not ctx["ready"]:
        st.warning("No data loaded. Run ingestion first.")
        return

    filtered: pd.DataFrame = ctx["filtered"]  # type: ignore[assignment]
    render_slice_hero_and_kpis()

    with chart_card(_copy("sub_latest_transactions"), caption=_copy("sub_activity_feed_caption")):
        render_transaction_table(filtered, limit=30)

    _render_section_intro(
        _copy("overview_kicker"),
        _copy("overview_title"),
        _copy("overview_copy"),
    )

    # --- Compact breakdown: chamber + transaction type as inline pill strips ---
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


    def _pill_strip(label: str, rows: pd.DataFrame, name_col: str, count_col: str, color: str) -> str:
        pills = []
        for _, row in rows.iterrows():
            n = f"{int(row[count_col]):,}"
            pills.append(
                f'<span style="display:inline-flex;align-items:center;gap:0.3rem;padding:0.3rem 0.7rem;'
                f'border-radius:999px;background:rgba(0,0,0,0.04);border:1px solid rgba(0,0,0,0.08);'
                f'font-size:0.88rem;font-weight:600;white-space:nowrap;">'
                f'<span style="color:{color};">{row[name_col]}</span>'
                f'<span style="color:{THEME["muted"]};font-weight:500;font-size:0.82rem;">{n}</span>'
                f"</span>"
            )
        inner = " ".join(pills)
        return (
            f'<div style="margin-bottom:0.6rem;">'
            f'<span style="font-size:0.76rem;font-weight:800;text-transform:uppercase;'
            f'letter-spacing:0.08em;color:{THEME["ink_soft"]};margin-right:0.55rem;">{label}</span>'
            f'{inner}</div>'
        )


    if not chamber_mix.empty or not transaction_mix.empty:
        parts = []
        if not chamber_mix.empty:
            parts.append(_pill_strip("By chamber", chamber_mix, "chamber", "transactions", THEME["teal"]))
        if not transaction_mix.empty:
            parts.append(_pill_strip("By type", transaction_mix, "transaction_type_label", "transactions", THEME["accent"]))
        st.markdown("".join(parts), unsafe_allow_html=True)

    _slice_min = filtered["transaction_date"].min()
    _slice_max = filtered["transaction_date"].max()
    _period_note = ""
    if pd.notna(_slice_min) and pd.notna(_slice_max):
        _period_note = f"Filter period: {_slice_min:%Y-%m-%d} to {_slice_max:%Y-%m-%d}."
    net_agg = _aggregate_net_trade_amount(filtered, top_n=20)
    with chart_card(
        "Net trade amount",
        caption=(
            "Net signed dollar flow per ticker in the current slice — green is net buying, "
            "red is net selling (signed disclosure range bounds per row)."
        ),
    ):
        if _period_note:
            st.caption(_period_note)
        if net_agg is None:
            st.info("No resolved tickers with directional (buy/sell) amounts in the current filter.")
        else:
            _net_table_cols = ["ticker", "first_trade", "last_trade", "direction", "net_label", "buy_label", "sell_label", "trades"]
            _net_table_cols = [c for c in _net_table_cols if c in net_agg.columns]
            net_view_col, net_dl_col = st.columns([5, 1], vertical_alignment="bottom")
            with net_view_col:
                net_view = st.radio(
                    "Net trade view",
                    ["Chart", "Table"],
                    horizontal=True,
                    key="home_net_trade_view",
                    label_visibility="collapsed",
                )
            with net_dl_col:
                _net_csv = net_agg[_net_table_cols].to_csv(index=False).encode("utf-8")
                st.download_button(
                    "Download CSV",
                    _net_csv,
                    file_name="net_trade_by_ticker.csv",
                    mime="text/csv",
                    use_container_width=True,
                    key="home_net_trade_download",
                    disabled=net_view != "Table",
                )
            if net_view == "Chart":
                net_chart = _build_net_trade_amount_chart(filtered, top_n=20, agg=net_agg)
                if net_chart is None:
                    st.info("No chart data available.")
                else:
                    st.altair_chart(net_chart, width="stretch")
            else:
                render_summary_table(
                    net_agg[_net_table_cols],
                    headers={
                        "ticker": "Ticker",
                        "first_trade": "First trade",
                        "last_trade": "Last trade",
                        "direction": "Direction",
                        "net_label": "Net amount",
                        "buy_label": "Gross buying",
                        "sell_label": "Gross selling",
                        "trades": "Trades",
                    },
                )

    # --- Monthly activity (full width) ---
    monthly_activity = (
        filtered.dropna(subset=["month"])
        .groupby("month", as_index=False)
        .agg(
            transactions=("member", "size"),
            amount_low=("amount_low", "sum"),
            amount_high=("amount_high", "sum"),
        )
        .sort_values("month")
    )

    with chart_card(_copy("sub_monthly_activity"), caption=_copy("chart_caption_monthly")):
        _ts_chart = _build_time_series_chart(monthly_activity) if not monthly_activity.empty else None
        if _ts_chart is None:
            st.info("No valid transaction dates in the current filter.")
        else:
            st.altair_chart(_ts_chart, width="stretch")

    # --- Top members + Top tickers (side by side, equal weight) ---
    top_members = (
        filtered.groupby("member", as_index=False)
        .agg(
            transactions=("member", "size"),
            amount_low=("amount_low", "sum"),
            amount_high=("amount_high", "sum"),
        )
        .sort_values(["transactions", "amount_high"], ascending=[False, False])
        .head(10)
    )
    top_tickers = (
        filtered.loc[filtered["ticker"] != ""]
        .groupby("ticker", as_index=False)
        .agg(
            transactions=("ticker", "size"),
            amount_low=("amount_low", "sum"),
            amount_high=("amount_high", "sum"),
        )
        .sort_values(["transactions", "amount_high"], ascending=[False, False])
        .head(10)
    )

    col_members, col_tickers = st.columns(2)
    with col_members:
        with chart_card(_copy("sub_top_members"), caption=_copy("chart_caption_rank_members")):
            if top_members.empty:
                st.info("No member activity for the current filter.")
            else:
                st.altair_chart(
                    _build_rank_chart(
                        top_members,
                        "member",
                        "Transaction count",
                        color=THEME["chart_series_primary"],
                        y_axis_title="Member",
                    ),
                    width="stretch",
                )
                render_summary_table(
                    add_disclosed_range_column(top_members, low_col="amount_low", high_col="amount_high")[
                        ["member", "transactions", "disclosed_range"]
                    ],
                    headers={
                        "member": "Member",
                        "transactions": "Trades",
                        "disclosed_range": "Disclosed range",
                    },
                )

    with col_tickers:
        with chart_card(_copy("sub_top_tickers"), caption=_copy("chart_caption_rank_tickers")):
            if top_tickers.empty:
                st.info("No resolved tickers in the current filter.")
            else:
                st.altair_chart(
                    _build_rank_chart(
                        top_tickers,
                        "ticker",
                        "Transaction count",
                        color=THEME["chart_series_secondary"],
                        y_axis_title="Ticker",
                    ),
                    width="stretch",
                )
                render_summary_table(
                    add_disclosed_range_column(top_tickers, low_col="amount_low", high_col="amount_high")[
                        ["ticker", "transactions", "disclosed_range"]
                    ],
                    headers={
                        "ticker": "Ticker",
                        "transactions": "Trades",
                        "disclosed_range": "Disclosed range",
                    },
                )

    st.space(1)
    st.subheader(_copy("overview_detail_heading"))
    st.caption(_copy("overview_detail_caption"))
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
        with chart_card(_copy("sub_ticker_who_when"), caption=_copy("ticker_chart_caption")):
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

        with chart_card(_copy("sub_ticker_3d"), caption=_copy("ticker_3d_caption")):
            fig_3d = _build_ticker_3d_figure(filtered, ticker_for_chart)
            if fig_3d is None:
                st.warning("Install **plotly** (`pip install plotly`) to use the 3D view.")
            else:
                st.plotly_chart(fig_3d, width="stretch")

        with chart_card(_copy("sub_cumulative_exposure"), caption=_copy("chart_caption_cumulative")):
            st.markdown(_cumulative_exposure_guide_html(ticker_for_chart), unsafe_allow_html=True)
            cum_chart, _cum_members = _build_member_cumulative_notional_chart(filtered, ticker_for_chart)
            if cum_chart is None:
                st.info(f"No dated transactions for ticker **{ticker_for_chart}** in the current slice.")
            else:
                st.altair_chart(cum_chart, width="stretch")
