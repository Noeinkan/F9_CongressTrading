from __future__ import annotations

import html
import re

import pandas as pd
import streamlit as st

from .components import _copy
from .constants import (
    _SIDEBAR_NO_ISSUER,
    _SIDEBAR_NO_TICKER,
)
from .data import transaction_type_filter_option

_QUARTER_OPTIONS = (1, 2, 3, 4)


def _available_years(data: pd.DataFrame) -> list[int]:
    dates = pd.to_datetime(data.get("transaction_date"), errors="coerce").dropna()
    if dates.empty:
        return []
    return sorted(int(y) for y in dates.dt.year.unique())


def _year_range_selection(
    years_available: list[int],
    year_from: int,
    year_to: int,
) -> list[int]:
    """Inclusive calendar-year range over available years (order-independent)."""
    lo, hi = min(year_from, year_to), max(year_from, year_to)
    return [y for y in years_available if lo <= y <= hi]


def _apply_period_filter(
    data: pd.DataFrame,
    *,
    selected_years: list[int] | None,
    selected_quarters: list[int] | None,
    all_years: list[int],
    all_quarters: tuple[int, ...] = _QUARTER_OPTIONS,
) -> pd.DataFrame:
    """Keep rows whose transaction_date falls in selected calendar years and quarters."""
    if data.empty or "transaction_date" not in data.columns:
        return data

    years_sel = list(selected_years or [])
    quarters_sel = list(selected_quarters or [])
    if not years_sel or not quarters_sel:
        return data.iloc[0:0].copy()

    if set(years_sel) >= set(all_years) and set(quarters_sel) >= set(all_quarters):
        return data

    dated = data.dropna(subset=["transaction_date"]).copy()
    if dated.empty:
        return dated

    tx_dates = pd.to_datetime(dated["transaction_date"], errors="coerce")
    mask = tx_dates.dt.year.isin(years_sel) & tx_dates.dt.quarter.isin(quarters_sel)
    return dated.loc[mask].copy()


def render_period_slicers_and_filter(data: pd.DataFrame) -> pd.DataFrame:
    """Compact year-range + quarter controls pinned in the top header bar."""
    years_available = _available_years(data)
    if not years_available:
        return data

    caption = html.escape(_copy("period_slicer_caption"))
    with st.container(key="period_toolbar"):
        slicer_cols = st.columns([0.3, 0.72, 0.06, 0.72, 2.15], vertical_alignment="center")
        with slicer_cols[0]:
            if st.button(
                "↺",
                key="dashboard_slicer_reset",
                help=f"{_copy('period_slicer_reset')}. {caption}",
                use_container_width=True,
            ):
                for key in (
                    "dashboard_slicer_year_from",
                    "dashboard_slicer_year_to",
                    "dashboard_slicer_quarter",
                    "dashboard_slicer_year",
                ):
                    st.session_state.pop(key, None)
                st.rerun()
        with slicer_cols[1]:
            year_from = st.selectbox(
                _copy("period_slicer_year_from"),
                years_available,
                index=0,
                format_func=str,
                label_visibility="collapsed",
                key="dashboard_slicer_year_from",
            )
        with slicer_cols[2]:
            st.markdown('<span class="period-toolbar-dash">–</span>', unsafe_allow_html=True)
        with slicer_cols[3]:
            year_to = st.selectbox(
                _copy("period_slicer_year_to"),
                years_available,
                index=len(years_available) - 1,
                format_func=str,
                label_visibility="collapsed",
                key="dashboard_slicer_year_to",
            )
        with slicer_cols[4]:
            selected_quarters = st.pills(
                "Quarter",
                list(_QUARTER_OPTIONS),
                selection_mode="multi",
                default=list(_QUARTER_OPTIONS),
                format_func=lambda q: f"Q{q}",
                key="dashboard_slicer_quarter",
            )

    years_sel = _year_range_selection(years_available, int(year_from), int(year_to))
    quarters_sel = list(selected_quarters or [])
    if not years_sel or not quarters_sel:
        st.warning("Select at least one year and one quarter to show data.")

    filtered = _apply_period_filter(
        data,
        selected_years=years_sel,
        selected_quarters=quarters_sel,
        all_years=years_available,
    )
    return filtered


def _sidebar_filter_label(title: str, copy: str = "", *, first: bool = False) -> None:
    extra = " filter-first" if first else ""
    title_html = html.escape(title)
    if copy:
        tip_html = html.escape(copy)
        st.markdown(
            f"""
            <div class="filter-section-label{extra} filter-has-tip">
                <span class="filter-label-text">{title_html}</span>
                <span class="filter-tip-popup" role="tooltip">{tip_html}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div class="filter-section-label{extra}">{title_html}</div>',
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
    return st.selectbox(
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
    st.markdown(
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
    st.markdown(
        f'<p class="sidebar-filters-heading">{_copy("sidebar_header")}</p>',
        unsafe_allow_html=True,
    )

    first_label = True

    chambers = sorted(value for value in filtered["chamber"].dropna().astype(str).unique() if value)
    if chambers:
        _sidebar_filter_label("Chamber", first=first_label)
        first_label = False
        selected_chambers = st.multiselect(
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
            _copy("sidebar_transaction_type_hint"),
        )
        type_options = [transaction_type_filter_option(r) for r in transaction_types]
        option_to_raw = dict(zip(type_options, transaction_types))
        default_opts = type_options
        selected_opts = st.multiselect(
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
        selected_asset_types = st.multiselect(
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
        selected_statuses = st.multiselect(
            "Review Status",
            review_statuses,
            default=review_statuses,
            label_visibility="collapsed",
            key="sidebar_review_status_filter",
        )
        filtered = filtered[filtered["review_status"].isin(selected_statuses)]

    _sidebar_filter_label("Minimum confidence (0–1)")
    confidence_threshold = st.slider(
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

