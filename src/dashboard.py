from __future__ import annotations

import streamlit as st

from .dashboard_shared import (
    _copy,
    _inject_styles,
    _render_empty_state,
    _render_hero,
    ensure_dashboard_authenticated,
    finalize_dashboard_slice,
    load_review_queue,
    load_transactions,
    setup_dashboard_session,
)

_PAGES_DIR = "src/dashboard_pages"


def render_dashboard() -> None:
    st.set_page_config(
        page_title=_copy("page_title"),
        page_icon=":material/account_balance:",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    ensure_dashboard_authenticated()
    _inject_styles(top_nav=True)

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

    pages = [
        st.Page(f"{_PAGES_DIR}/home.py", title="Home", icon=":material/home:", default=True),
        st.Page(f"{_PAGES_DIR}/members.py", title="Members", icon=":material/groups:"),
        st.Page(f"{_PAGES_DIR}/tickers.py", title="Tickers", icon=":material/candlestick_chart:"),
        st.Page(f"{_PAGES_DIR}/patterns.py", title="Patterns", icon=":material/insights:"),
        st.Page(f"{_PAGES_DIR}/review.py", title="Review Queue", icon=":material/fact_check:"),
        st.Page(f"{_PAGES_DIR}/raw_data.py", title="Raw Data", icon=":material/table_chart:"),
    ]
    pg = st.navigation(pages, position="top")
    finalize_dashboard_slice()
    pg.run()
