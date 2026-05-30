from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import streamlit as st

from .constants import DASHBOARD_COPY, THEME
from .kpi_sparklines import KpiSpec, month_over_month_delta

def _copy(key: str) -> str:
    return DASHBOARD_COPY[key]


def _metric_card(label: str, value: str, detail: str, *, accent: bool = False) -> str:
    tone = "metric-card accent" if accent else "metric-card"
    return f"""
    <div class=\"{tone}\">
        <div class=\"metric-label\">{label}</div>
        <div class=\"metric-value\">{value}</div>
        <div class=\"metric-subtle\">{detail}</div>
    </div>
    """


def _normalize_kpi_specs(
    specs: list[KpiSpec | tuple[str, str, str]],
) -> list[KpiSpec]:
    out: list[KpiSpec] = []
    for item in specs:
        if isinstance(item, KpiSpec):
            out.append(item)
        else:
            label, value, detail = item
            out.append(KpiSpec(label=label, value=value, detail=detail))
    return out


def render_kpi_row(
    specs: list[KpiSpec | tuple[str, str, str]],
    *,
    accent_index: int | None = None,
) -> None:
    """KPI strip with optional sparklines (``st.metric`` + ``chart_data``)."""
    normalized = _normalize_kpi_specs(specs)
    if not normalized:
        return
    cols = st.columns(len(normalized))
    for i, spec in enumerate(normalized):
        with cols[i]:
            if spec.sparkline:
                delta = spec.delta
                if delta is None:
                    delta = month_over_month_delta(spec.sparkline, percent=spec.delta_percent)
                st.metric(
                    spec.label,
                    spec.value,
                    delta=delta,
                    help=spec.detail,
                    border=True,
                    chart_data=spec.sparkline,
                    chart_type=spec.chart_type,
                )
            elif accent_index == i:
                st.markdown(
                    _metric_card(spec.label, spec.value, spec.detail, accent=True),
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    _metric_card(spec.label, spec.value, spec.detail),
                    unsafe_allow_html=True,
                )


@contextmanager
def chart_card(title: str, *, caption: str | None = None) -> Iterator[None]:
    """Bordered Streamlit container for a chart or table block."""
    with st.container(border=True):
        st.markdown(f"**{title}**")
        if caption:
            st.caption(caption)
        yield


def render_chart_section(title: str, *, caption: str | None = None) -> None:
    """Lightweight section title without a card (prefer ``chart_card`` for visuals)."""
    st.subheader(title)
    if caption:
        st.caption(caption)


def _render_section_intro(kicker: str, title: str, copy: str) -> None:
    st.markdown(
        f"""
        <div class=\"section-card\">
            <div class=\"section-kicker\">{kicker}</div>
            <div class=\"section-title\">{title}</div>
            <div class=\"section-copy\">{copy}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_hero(
    *,
    transaction_source: str,
    review_source: str,
    total_transactions: int | None = None,
    tracked_tickers: int | None = None,
    open_reviews: int | None = None,
    avg_confidence: float | None = None,
    active_chambers: str | None = None,
    coverage_label: str | None = None,
    latest_filing_label: str | None = None,
    empty: bool = False,
) -> None:
    if empty:
        st.markdown(
            f"""
            <section class="dashboard-shell">
                <div class="eyebrow">{_copy("eyebrow")}</div>
                <h1 class="hero-title">{_copy("empty_hero_title")}</h1>
                <p class="hero-copy">{_copy("empty_hero_copy")}</p>
                <div class="hero-meta">
                    <div class="meta-pill">Transactions source: {transaction_source}</div>
                    <div class="meta-pill">Review source: {review_source}</div>
                </div>
            </section>
            """,
            unsafe_allow_html=True,
        )
        return

    st.markdown(
        f"""
        <section class="dashboard-shell">
            <div class="hero-grid">
                <div>
                    <div class="eyebrow">{_copy("eyebrow")}</div>
                    <h1 class="hero-title">{_copy("hero_title")}</h1>
                    <p class="hero-copy">{_copy("hero_copy")}</p>
                    <div class="hero-meta">
                        <div class="meta-pill">Visible chambers: {active_chambers}</div>
                        <div class="meta-pill">Transaction coverage: {coverage_label}</div>
                        <div class="meta-pill">Transactions source: {transaction_source}</div>
                        <div class="meta-pill">Review source: {review_source}</div>
                    </div>
                </div>
                <div class="hero-aside">
                    <div class="hero-aside-label">{_copy("current_slice")}</div>
                    <div class="hero-aside-value">{total_transactions:,} trades</div>
                    <div>Latest filing: {latest_filing_label}</div>
                    <div style="margin-top:0.35rem; color: {THEME['hero_ink_soft']};">
                        {open_reviews:,} open reviews · {tracked_tickers:,} tickers · {avg_confidence:.0%} avg confidence
                    </div>
                </div>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )

def _render_empty_state() -> None:
    st.warning(_copy("empty_state"))
    st.code(
        "\n".join(
            [
                "python -m src.main ingest-all",
                "python -m src.main export-csv --out data/congress_trades.csv",
                "python -m src.main dashboard",
            ]
        ),
        language="bash",
    )

