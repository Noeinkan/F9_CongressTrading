from __future__ import annotations

import pandas as pd
import streamlit as st

from .components import _copy, _metric_card, _render_hero
from .constants import THEME
from .data import _format_currency, load_review_queue, load_transactions
from .filters import _apply_filters_fragment

def _filter_review_queue(review_queue: pd.DataFrame, filtered_transactions: pd.DataFrame) -> pd.DataFrame:
    if review_queue.empty or filtered_transactions.empty:
        return review_queue.iloc[0:0].copy()

    review_index = review_queue.assign(
        _review_key=(
            review_queue["member"].astype(str)
            + "|"
            + review_queue["asset_name_raw"].astype(str)
            + "|"
            + review_queue["transaction_type"].astype(str)
            + "|"
            + review_queue["amount_range_raw"].astype(str)
            + "|"
            + review_queue["transaction_date"].astype(str)
        )
    )
    filtered_index = filtered_transactions.assign(
        _review_key=(
            filtered_transactions["member"].astype(str)
            + "|"
            + filtered_transactions["asset_name_raw"].astype(str)
            + "|"
            + filtered_transactions["transaction_type"].astype(str)
            + "|"
            + filtered_transactions["amount_range_raw"].astype(str)
            + "|"
            + filtered_transactions["transaction_date"].astype(str)
        )
    )
    return review_index[review_index["_review_key"].isin(filtered_index["_review_key"])].drop(columns=["_review_key"])

def get_dashboard_context() -> dict[str, object]:
    return {
        "transactions": st.session_state.get("dashboard_transactions", pd.DataFrame()),
        "filtered": st.session_state.get("dashboard_filtered", pd.DataFrame()),
        "review": st.session_state.get("dashboard_review", pd.DataFrame()),
        "transaction_source": st.session_state.get("dashboard_transaction_source", ""),
        "review_source": st.session_state.get("dashboard_review_source", ""),
        "ready": bool(st.session_state.get("dashboard_ready", False)),
    }


def setup_dashboard_session() -> bool:
    """Load data, apply sidebar filters, populate session state. Returns False if empty dataset."""
    transactions, transaction_source = load_transactions()
    review_queue, review_source = load_review_queue(transactions)
    st.session_state["dashboard_transactions"] = transactions
    st.session_state["dashboard_transaction_source"] = transaction_source
    st.session_state["dashboard_review_source"] = review_source

    if transactions.empty:
        st.session_state["dashboard_ready"] = False
        st.session_state["dashboard_filtered"] = transactions
        st.session_state["dashboard_review"] = review_queue
        return False

    with st.sidebar:
        filtered = _apply_filters_fragment(transactions)
    filtered_review = _filter_review_queue(review_queue, filtered)
    st.session_state["dashboard_ready"] = True
    st.session_state["dashboard_filtered"] = filtered
    st.session_state["dashboard_review"] = filtered_review
    return True


def render_slice_hero_and_kpis() -> None:
    ctx = get_dashboard_context()
    filtered: pd.DataFrame = ctx["filtered"]  # type: ignore[assignment]
    if filtered.empty:
        return
    total_transactions = len(filtered)
    total_members = filtered["member"].nunique()
    tracked_tickers = filtered.loc[filtered["ticker"] != "", "ticker"].nunique()
    filtered_review: pd.DataFrame = ctx["review"]  # type: ignore[assignment]
    open_reviews = int((filtered_review["status"] == "open").sum()) if not filtered_review.empty else 0
    estimated_value = filtered["estimated_value"].sum(skipna=True)
    avg_confidence = filtered["confidence_score"].mean() if total_transactions else 0.0
    active_chambers = ", ".join(sorted(filtered["chamber"].dropna().astype(str).unique())) or _copy("no_chamber_selected")
    latest_filing = filtered["filing_date"].max()
    visible_date_min = filtered["transaction_date"].min()
    visible_date_max = filtered["transaction_date"].max()
    coverage_label = _copy("no_dated_trades")
    latest_filing_label = "n/a"
    if pd.notna(visible_date_min) and pd.notna(visible_date_max):
        coverage_label = f"{visible_date_min:%Y-%m-%d} to {visible_date_max:%Y-%m-%d}"
    if pd.notna(latest_filing):
        latest_filing_label = f"{latest_filing:%Y-%m-%d}"

    _render_hero(
        transaction_source=str(ctx["transaction_source"]),
        review_source=str(ctx["review_source"]),
        total_transactions=total_transactions,
        tracked_tickers=tracked_tickers,
        open_reviews=open_reviews,
        avg_confidence=avg_confidence,
        active_chambers=active_chambers,
        coverage_label=coverage_label,
        latest_filing_label=latest_filing_label,
    )
    metric_columns = st.columns(5)
    metric_columns[0].markdown(
        _metric_card("Transactions", f"{total_transactions:,}", "Rows currently visible after filters."),
        unsafe_allow_html=True,
    )
    metric_columns[1].markdown(
        _metric_card("Members", f"{total_members:,}", "Distinct filers represented in the visible slice."),
        unsafe_allow_html=True,
    )
    metric_columns[2].markdown(
        _metric_card("Tickers", f"{tracked_tickers:,}", "Resolved instruments ready for analysis."),
        unsafe_allow_html=True,
    )
    metric_columns[3].markdown(
        _metric_card("Open Reviews", f"{open_reviews:,}", "Records still flagged for manual validation."),
        unsafe_allow_html=True,
    )
    metric_columns[4].markdown(
        _metric_card(
            "Estimated Midpoint",
            _format_currency(estimated_value),
            f"Average confidence {avg_confidence:.0%}.",
            accent=True,
        ),
        unsafe_allow_html=True,
    )
    st.divider()


