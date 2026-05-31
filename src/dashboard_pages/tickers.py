from __future__ import annotations



import pandas as pd

import streamlit as st



from src.dashboard_shared import (
    KpiSpec,

    _build_member_cumulative_notional_chart,

    _build_ticker_member_timeline,

    _copy,

    _cumulative_exposure_guide_html,

    _render_section_intro,

    _ticker_timeline_color_key_html,

    add_disclosed_range_column,
    format_disclosed_range,
    sum_amount_high,
    sum_amount_low,

    build_price_overlay_figure,

    chart_card,

    format_count,

    format_currency_compact,
    external_quote_links_markdown,

    get_dashboard_context,

    load_issuer_info,
    load_ticker_details,

    monthly_series,

    render_kpi_row,

    render_summary_table,
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



qp_ticker = st.query_params.get("ticker", "").strip().upper()
_qp_override = ""
if qp_ticker:
    if qp_ticker in tickers_available:
        default_ticker = qp_ticker
        st.session_state["dashboard_selected_ticker"] = qp_ticker
        st.session_state["tickers_page_select"] = qp_ticker
    else:
        default_ticker = st.session_state.get("dashboard_selected_ticker")
        _qp_override = qp_ticker
    st.query_params.pop("ticker", None)
else:
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

    manual = st.text_input(
        "Override symbol",
        value=_qp_override,
        placeholder="e.g. NVDA",
        key="tickers_page_manual",
    ).strip().upper()



ticker = manual if manual else selected

st.session_state["dashboard_selected_ticker"] = ticker



slice_df = filtered[filtered["ticker"].astype(str).str.upper() == ticker.upper()]

if slice_df.empty:

    st.info(f"No trades for **{ticker}** in the current slice.")

    st.stop()


issuer_info = load_issuer_info(ticker)
company = load_ticker_details(ticker)
_name = (company.get("name") or issuer_info.get("issuer_name") or "").strip()
_desc = (company.get("description") or "").strip()
_employees = company.get("total_employees")
_market_cap = company.get("market_cap")
_exchange = (company.get("primary_exchange") or "").strip()
_sector = (issuer_info.get("sector") or "").strip()
_sic = (company.get("sic_description") or issuer_info.get("industry") or "").strip()
_industry_label = " · ".join(x for x in (_sector, _sic) if x)
_homepage = (company.get("homepage_url") or "").strip()
_has_company = bool(
    _name
    or _desc
    or _employees is not None
    or _market_cap is not None
    or _exchange
    or _industry_label
    or _homepage
)

_quote_links = external_quote_links_markdown(ticker)

if _has_company:
    with st.container(border=True):
        title_bits = [f"**{_name or ticker}**", f"`{ticker}`"]
        if _exchange:
            title_bits.append(f"· {_exchange}")
        if _homepage:
            title_bits.append(f"· [Website]({_homepage})")
        st.markdown(" ".join(title_bits))
        if _quote_links:
            st.markdown(_quote_links)
        stat_cols = st.columns(3)
        with stat_cols[0]:
            st.caption("Market cap")
            st.markdown(
                format_currency_compact(_market_cap) if _market_cap is not None else "—"
            )
        with stat_cols[1]:
            st.caption("Employees")
            st.markdown(format_count(_employees) if _employees is not None else "—")
        with stat_cols[2]:
            st.caption("Sector / industry")
            st.markdown(_industry_label or "—")
        _show_desc = _desc and _desc.strip().upper() != (_name or "").strip().upper() and len(_desc) >= 50
        if _show_desc:
            _preview = _desc if len(_desc) <= 200 else _desc[:197].rstrip() + "…"
            st.caption(_preview)
            if len(_desc) > 200:
                with st.expander("Full description", expanded=False):
                    st.write(_desc)
elif _quote_links:
    st.markdown(_quote_links)


buys = int((slice_df["transaction_type"].astype(str).str.strip() == "P").sum())

sells = int(slice_df["transaction_type"].astype(str).str.strip().str.startswith("S").sum())



render_kpi_row(

    [

        KpiSpec(

            "Trades",

            format_count(len(slice_df)),

            "Disclosures for this ticker",

            sparkline=monthly_series(slice_df, "transactions") or None,

        ),

        KpiSpec(

            "Members",

            format_count(slice_df["member"].nunique()),

            "Distinct filers",

            sparkline=monthly_series(slice_df, "members") or None,

        ),

        (

            "Buy / sell",

            f"{format_count(buys)} / {format_count(sells)}",

            "Purchase vs sale disclosure codes",

        ),

        KpiSpec(

            "Disclosed range",

            format_disclosed_range(sum_amount_low(slice_df), sum_amount_high(slice_df)),

            "Sum of amount_low – sum of amount_high for this ticker",

            sparkline=monthly_series(slice_df, "disclosed_amount_high") or None,

            delta_percent=True,

        ),

    ]

)



with chart_card("Who traded this ticker"):

    who = ticker_member_breakdown(filtered, ticker)

    if who.empty:

        st.info("No member breakdown available.")

    else:

        _who = who.copy()

        _who = add_disclosed_range_column(_who, low_col="amount_low_sum", high_col="amount_high_sum")

        render_summary_table(
            _who,
            columns=[
                "member",
                "buy",
                "sell",
                "call",
                "put",
                "trades",
                "disclosed_range",
                "first_trade",
                "last_trade",
            ],
            headers={
                "member": "Member",
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

    "Price & trade overlay",

    caption="Uses `polygon_daily_bar_cache` only — warm via CLI; no live API calls from the dashboard.",

):

    price_fig = build_price_overlay_figure(filtered, ticker)

    if price_fig is None:

        st.info("No Polygon bars cached for this ticker. Trade timeline below still works.")

    else:

        st.plotly_chart(price_fig, width="stretch")



with chart_card(

    "Member timeline",

    caption="Each dot is one disclosure; color is transaction type (see legend).",

):

    ticker_chart = _build_ticker_member_timeline(filtered, ticker)

    if ticker_chart is None:

        st.info("No dated transactions for this ticker.")

    else:

        labs = slice_df["transaction_type"].map(transaction_type_display_label).astype(str).unique().tolist()

        preferred = ["Buy", "Sell", "Sell (partial)", "Exchange", "Unknown"]

        color_key_order = [x for x in preferred if x in labs] + sorted(x for x in labs if x not in preferred)

        st.markdown(_ticker_timeline_color_key_html(color_key_order), unsafe_allow_html=True)

        st.altair_chart(ticker_chart, width="stretch")



with chart_card(_copy("sub_cumulative_exposure"), caption=_copy("chart_caption_cumulative")):

    st.markdown(_cumulative_exposure_guide_html(ticker), unsafe_allow_html=True)

    cum_chart, _ = _build_member_cumulative_notional_chart(filtered, ticker)

    if cum_chart is None:

        st.info("No cumulative exposure series for this ticker.")

    else:

        st.altair_chart(cum_chart, width="stretch")

