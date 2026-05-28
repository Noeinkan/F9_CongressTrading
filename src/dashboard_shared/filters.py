from __future__ import annotations

from datetime import date
import re

import pandas as pd
import streamlit as st

from .components import _copy
from .constants import (
    DEFAULT_TRANSACTION_FILTER_START,
    _SIDEBAR_NO_ISSUER,
    _SIDEBAR_NO_TICKER,
)
from .data import transaction_type_filter_option

def _sidebar_full_dataset_stats_compact(data: pd.DataFrame) -> None:
    transaction_count = len(data)
    member_count = data["member"].nunique()
    ticker_count = data.loc[data["ticker"] != "", "ticker"].nunique()
    valid_dates = data["transaction_date"].dropna()
    coverage = _copy("no_dated_trades")
    if not valid_dates.empty:
        coverage = f"{valid_dates.min():%Y-%m-%d} → {valid_dates.max():%Y-%m-%d}"

    st.markdown(
        f"""
        <div class="sidebar-stat-grid-compact">
            <div class="sidebar-stat-tiny">
                <div class="sidebar-stat-label">Txns</div>
                <div class="sidebar-stat-value">{transaction_count:,}</div>
            </div>
            <div class="sidebar-stat-tiny">
                <div class="sidebar-stat-label">Members</div>
                <div class="sidebar-stat-value">{member_count:,}</div>
            </div>
            <div class="sidebar-stat-tiny">
                <div class="sidebar-stat-label">Tickers</div>
                <div class="sidebar-stat-value">{ticker_count:,}</div>
            </div>
            <div class="sidebar-stat-tiny">
                <div class="sidebar-stat-label">Dates</div>
                <div class="sidebar-stat-value">{coverage}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _sidebar_filter_label(title: str, copy: str = "", *, first: bool = False) -> None:
    extra = " filter-first" if first else ""
    if copy:
        st.sidebar.markdown(
            f"""
            <div class="filter-section-label{extra}">{title}</div>
            <div class="filter-section-copy">{copy}</div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.sidebar.markdown(
            f'<div class="filter-section-label{extra}">{title}</div>',
            unsafe_allow_html=True,
        )


def _sidebar_typeahead_select(
    *,
    title: str,
    hint: str,
    options: list[str],
    widget_key: str,
    first: bool,
    placeholder: str,
) -> str | None:
    """Single Streamlit combobox: st.selectbox with index=None + accept_new_options (see docs for st.selectbox)."""
    _sidebar_filter_label(title, hint, first=first)
    return st.sidebar.selectbox(
        title,
        options,
        index=None,
        placeholder=placeholder,
        accept_new_options=True,
        label_visibility="collapsed",
        key=widget_key,
    )


def _sidebar_slice_bar(filtered: pd.DataFrame) -> None:
    visible_records = len(filtered)
    visible_members = filtered["member"].nunique()
    avg_confidence = filtered["confidence_score"].mean() if visible_records else 0.0
    unresolved = int((filtered["review_status"] != "resolved").sum()) if visible_records else 0
    title = _copy("sidebar_slice_summary_title")
    st.sidebar.markdown(
        f"""
        <div class="sidebar-slice-bar">
            <span><strong>{title}</strong> {visible_records:,} rows</span>
            <span class="sep">·</span>
            <span>{visible_members:,} members</span>
            <span class="sep">·</span>
            <span>{avg_confidence:.0%} avg conf.</span>
            <span class="sep">·</span>
            <span>{unresolved:,} need review</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


@st.fragment
def _apply_filters_fragment(data: pd.DataFrame) -> pd.DataFrame:
    return _apply_filters(data)


def _apply_filters(data: pd.DataFrame) -> pd.DataFrame:
    """Scope first (dates, chamber), then typeahead selects (member, ticker, issuer), facets, confidence."""
    filtered = data.copy()
    st.sidebar.markdown(
        f'<p class="sidebar-filters-heading">{_copy("sidebar_header")}</p>',
        unsafe_allow_html=True,
    )
    with st.sidebar.expander(_copy("sidebar_dataset_expander"), expanded=False):
        st.markdown(
            f'<p class="sidebar-expander-caption">{_copy("sidebar_dataset_expander_caption")}</p>',
            unsafe_allow_html=True,
        )
        _sidebar_full_dataset_stats_compact(data)

    first_label = True

    valid_dates = filtered["transaction_date"].dropna()
    if not valid_dates.empty:
        min_date = valid_dates.min().date()
        max_date = valid_dates.max().date()
        today = date.today()
        picker_max = max(max_date, today)
        default_start = max(min_date, DEFAULT_TRANSACTION_FILTER_START)
        default_end = min(max_date, today)
        if default_start > default_end:
            default_start, default_end = min_date, max_date
        _sidebar_filter_label("Transaction dates", first=first_label)
        first_label = False
        date_range = st.sidebar.date_input(
            "Transaction Date Range",
            value=(default_start, default_end),
            min_value=min_date,
            max_value=picker_max,
            label_visibility="collapsed",
            key="sidebar_transaction_date_filter",
        )
        if isinstance(date_range, tuple) and len(date_range) == 2:
            start_date, end_date = date_range
            filtered = filtered[
                filtered["transaction_date"].between(pd.Timestamp(start_date), pd.Timestamp(end_date))
            ]

    chambers = sorted(value for value in filtered["chamber"].dropna().astype(str).unique() if value)
    if chambers:
        _sidebar_filter_label("Chamber", first=first_label)
        first_label = False
        selected_chambers = st.sidebar.multiselect(
            "Chamber",
            chambers,
            default=chambers,
            label_visibility="collapsed",
            key="sidebar_chamber_filter",
        )
        filtered = filtered[filtered["chamber"].isin(selected_chambers)]

    members_sorted = sorted({str(m).strip() for m in filtered["member"].dropna().unique() if str(m).strip()})
    if members_sorted:
        member_choice = _sidebar_typeahead_select(
            title=_copy("sidebar_pick_member_label"),
            hint=_copy("sidebar_member_filter_hint"),
            options=members_sorted,
            widget_key="sidebar_filter_member",
            first=first_label,
            placeholder=_copy("sidebar_member_filter_placeholder"),
        )
        first_label = False
        if member_choice:
            pat = re.escape(str(member_choice))
            mcol = filtered["member"].astype(str).str.strip()
            filtered = filtered[mcol.str.contains(pat, case=False, na=False, regex=True)]

    tickers_nonempty = sorted(
        {str(t).strip() for t in filtered["ticker"].dropna().unique() if str(t).strip()}
    )
    has_blank_ticker = filtered["ticker"].fillna("").astype(str).str.strip().eq("").any()
    if tickers_nonempty or has_blank_ticker:
        ticker_options: list[str] = []
        if has_blank_ticker:
            ticker_options.append(_SIDEBAR_NO_TICKER)
        ticker_options.extend(tickers_nonempty)
        ticker_choice = _sidebar_typeahead_select(
            title=_copy("sidebar_pick_ticker_label"),
            hint=_copy("sidebar_ticker_filter_hint"),
            options=ticker_options,
            widget_key="sidebar_filter_ticker",
            first=first_label,
            placeholder=_copy("sidebar_ticker_filter_placeholder"),
        )
        first_label = False
        if ticker_choice in (None, ""):
            pass
        elif ticker_choice in (_SIDEBAR_NO_TICKER, "-"):
            filtered = filtered[filtered["ticker"].fillna("").astype(str).str.strip().eq("")]
        else:
            tcol = filtered["ticker"].fillna("").astype(str).str.strip()
            pat = re.escape(str(ticker_choice))
            filtered = filtered[tcol.str.contains(pat, case=False, na=False, regex=True)]

    issuers_nonempty = sorted(
        {str(i).strip() for i in filtered["issuer_name"].dropna().unique() if str(i).strip()}
    )
    has_blank_issuer = filtered["issuer_name"].fillna("").astype(str).str.strip().eq("").any()
    if issuers_nonempty or has_blank_issuer:
        issuer_options: list[str] = []
        if has_blank_issuer:
            issuer_options.append(_SIDEBAR_NO_ISSUER)
        issuer_options.extend(issuers_nonempty)
        issuer_choice = _sidebar_typeahead_select(
            title=_copy("sidebar_pick_issuer_label"),
            hint=_copy("sidebar_issuer_filter_hint"),
            options=issuer_options,
            widget_key="sidebar_filter_issuer",
            first=first_label,
            placeholder=_copy("sidebar_issuer_filter_placeholder"),
        )
        first_label = False
        icol = filtered["issuer_name"].fillna("").astype(str).str.strip()
        if issuer_choice in (None, ""):
            pass
        elif issuer_choice in (_SIDEBAR_NO_ISSUER, "-"):
            filtered = filtered[icol.eq("")]
        elif issuer_choice:
            pat = re.escape(str(issuer_choice))
            filtered = filtered[icol.str.contains(pat, case=False, na=False, regex=True)]

    transaction_types = sorted(value for value in filtered["transaction_type"].dropna().astype(str).unique() if value)
    if transaction_types:
        _sidebar_filter_label(
            "Transaction type",
            "P = Buy, S = Sell (chips show full words plus the filing code).",
        )
        type_options = [transaction_type_filter_option(r) for r in transaction_types]
        option_to_raw = dict(zip(type_options, transaction_types))
        default_opts = type_options
        selected_opts = st.sidebar.multiselect(
            "Transaction Type",
            type_options,
            default=default_opts,
            label_visibility="collapsed",
            key="sidebar_transaction_type_filter",
        )
        selected_raws = [option_to_raw[o] for o in selected_opts if o in option_to_raw]
        if selected_raws:
            filtered = filtered[filtered["transaction_type"].isin(selected_raws)]

    asset_types = sorted(value for value in filtered["asset_type"].dropna().astype(str).unique() if value)
    if asset_types:
        _sidebar_filter_label("Asset type")
        selected_asset_types = st.sidebar.multiselect(
            "Asset Type",
            asset_types,
            default=asset_types,
            label_visibility="collapsed",
            key="sidebar_asset_type_filter",
        )
        filtered = filtered[filtered["asset_type"].isin(selected_asset_types)]

    review_statuses = sorted(value for value in filtered["review_status"].dropna().astype(str).unique() if value)
    if review_statuses:
        _sidebar_filter_label("Review status")
        selected_statuses = st.sidebar.multiselect(
            "Review Status",
            review_statuses,
            default=review_statuses,
            label_visibility="collapsed",
            key="sidebar_review_status_filter",
        )
        filtered = filtered[filtered["review_status"].isin(selected_statuses)]

    _sidebar_filter_label("Minimum confidence (0–1)")
    confidence_threshold = st.sidebar.slider(
        "Minimum Confidence",
        min_value=0.0,
        max_value=1.0,
        value=0.0,
        step=0.05,
        label_visibility="collapsed",
        key="sidebar_confidence_filter",
    )
    filtered = filtered[filtered["confidence_score"] >= confidence_threshold]

    _sidebar_slice_bar(filtered)
    return filtered

