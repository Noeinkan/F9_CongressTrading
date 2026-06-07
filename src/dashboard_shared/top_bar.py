from __future__ import annotations

import html
from collections.abc import Callable

import pandas as pd
import streamlit as st

from .components import _copy
from .filters import (
    _LOOKBACK_OPTIONS,
    _QUARTER_OPTIONS,
    _apply_period_filter,
    _available_years,
    _lookback_years,
)

NAV_ITEMS: tuple[tuple[str, str], ...] = (
    ("home", "Home"),
    ("members", "Members"),
    ("tickers", "Tickers"),
    ("patterns", "Patterns"),
    ("review", "Review Queue"),
    ("raw_data", "Raw Data"),
)

PAGE_KEYS: frozenset[str] = frozenset(key for key, _ in NAV_ITEMS)
DEFAULT_PAGE = "home"


def resolve_active_page(page_param: str | None) -> str:
    if page_param and page_param in PAGE_KEYS:
        return page_param
    return DEFAULT_PAGE


def build_top_bar_brand_html(*, brand: str | None = None) -> str:
    brand_label = html.escape(brand or _copy("nav_brand"))
    return f'<div class="dtb-brand">{brand_label}</div>'


def build_top_bar_html(*, active_page: str, brand: str | None = None) -> str:
    """Legacy HTML builder — kept for tests; nav uses Streamlit buttons in render_top_bar."""
    brand_html = build_top_bar_brand_html(brand=brand)
    links: list[str] = []
    for key, label in NAV_ITEMS:
        attrs = ""
        if key == active_page:
            attrs = ' aria-current="page"'
        links.append(
            f'<span class="dtb-nav-item"{attrs} data-page="{html.escape(key)}">{html.escape(label)}</span>'
        )
    nav_inner = " ".join(links)
    return f"""<div class="dashboard-top-bar-inner">
    {brand_html}
    <nav class="dtb-nav" aria-label="Dashboard pages">
        {nav_inner}
    </nav>
</div>"""


def _navigate_to_page(page_key: str) -> None:
    st.query_params["page"] = page_key
    st.rerun()


def render_top_bar(*, active_page: str) -> None:
    with st.container(key="dashboard_top_bar"):
        brand_col, nav_col = st.columns([1.4, 5.6], vertical_alignment="center", gap="small")
        with brand_col:
            st.markdown(build_top_bar_brand_html(), unsafe_allow_html=True)
        with nav_col:
            nav_cols = st.columns(len(NAV_ITEMS), gap="small")
            for col, (key, label) in zip(nav_cols, NAV_ITEMS):
                with col:
                    if key == active_page:
                        st.markdown(
                            f'<span class="dtb-nav-active" aria-current="page">{html.escape(label)}</span>',
                            unsafe_allow_html=True,
                        )
                    elif st.button(
                        label,
                        key=f"dashboard_nav_{key}",
                        type="tertiary",
                        use_container_width=True,
                    ):
                        _navigate_to_page(key)


def render_sidebar_period_slicer(data: pd.DataFrame) -> pd.DataFrame:
    """Lookback + quarter controls in the left sidebar."""
    years_available = _available_years(data)
    if not years_available:
        return data

    lookback_labels = [label for label, _ in _LOOKBACK_OPTIONS]
    caption = html.escape(_copy("sidebar_period_caption"))
    with st.sidebar:
        st.header(_copy("sidebar_period_header"))
        st.caption(_copy("sidebar_period_caption"))
        if st.button(
            "↺ Reset period",
            key="dashboard_slicer_reset",
            help=f"{_copy('period_slicer_reset')}. {caption}",
            use_container_width=True,
        ):
            for key in (
                "dashboard_slicer_lookback",
                "dashboard_slicer_quarter",
            ):
                st.session_state.pop(key, None)
            st.rerun()
        lookback_choice = st.selectbox(
            "Period",
            lookback_labels,
            index=1,
            key="dashboard_slicer_lookback",
        )
        selected_quarters = st.pills(
            "Quarter",
            list(_QUARTER_OPTIONS),
            selection_mode="multi",
            default=list(_QUARTER_OPTIONS),
            format_func=lambda q: f"Q{q}",
            key="dashboard_slicer_quarter",
        )

    lookback_n = dict(_LOOKBACK_OPTIONS).get(lookback_choice)
    years_sel = _lookback_years(data, lookback_n, years_available)
    quarters_sel = list(selected_quarters or [])
    if not years_sel or not quarters_sel:
        st.sidebar.warning("Select at least one period and one quarter to show data.")

    return _apply_period_filter(
        data,
        selected_years=years_sel,
        selected_quarters=quarters_sel,
        all_years=years_available,
    )


def _page_renderers() -> dict[str, Callable[[dict[str, object]], None]]:
    from src.dashboard_pages import home, members, patterns, raw_data, review, tickers

    return {
        "home": home.render,
        "members": members.render,
        "tickers": tickers.render,
        "patterns": patterns.render,
        "review": review.render,
        "raw_data": raw_data.render,
    }


_PAGE_RENDERERS: dict[str, Callable[[dict[str, object]], None]] | None = None


def get_page_renderers() -> dict[str, Callable[[dict[str, object]], None]]:
    global _PAGE_RENDERERS
    if _PAGE_RENDERERS is None:
        _PAGE_RENDERERS = _page_renderers()
    return _PAGE_RENDERERS


def dispatch_to_page(page_key: str, ctx: dict[str, object]) -> None:
    key = resolve_active_page(page_key)
    get_page_renderers()[key](ctx)


def read_active_page_from_query() -> str:
    raw = st.query_params.get("page")
    if isinstance(raw, list):
        raw = raw[0] if raw else None
    return resolve_active_page(raw)
