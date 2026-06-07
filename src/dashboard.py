from __future__ import annotations

import streamlit as st

from .dashboard_shared import (
    _copy,
    _inject_styles,
    _render_empty_state,
    _render_hero,
    dispatch_to_page,
    ensure_dashboard_authenticated,
    finalize_dashboard_slice,
    get_dashboard_context,
    load_review_queue,
    load_transactions,
    read_active_page_from_query,
    render_top_bar,
    setup_dashboard_session,
)


def render_dashboard() -> None:
    st.set_page_config(
        page_title=_copy("page_title"),
        page_icon=":material/account_balance:",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    ensure_dashboard_authenticated()
    _inject_styles(top_bar=True)

    transactions, transaction_source = load_transactions()
    review_queue, review_source = load_review_queue(transactions)

    if transactions.empty:
        _render_hero(transaction_source=transaction_source, review_source=review_source, empty=True)
        _render_empty_state()
        return

    if not setup_dashboard_session():
        _render_hero(transaction_source=transaction_source, review_source=review_source, empty=True)
        _render_empty_state()
        return

    finalize_dashboard_slice()
    active_page = read_active_page_from_query()
    render_top_bar(active_page=active_page)
    dispatch_to_page(active_page, get_dashboard_context())
