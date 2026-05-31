from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from .constants import THEME

def _streamlit_theme_is_dark() -> bool:
    try:
        return getattr(st.context.theme, "type", None) == "dark"
    except Exception:
        return False


def _buy_sell_cell_style(value: object, *, dark: bool) -> str:
    """Muted buy/sell chips aligned with THEME (teal / accent / navy / gold), light vs dark Streamlit."""
    label = "" if value is None or (isinstance(value, float) and pd.isna(value)) else str(value).strip()
    t = THEME
    # Shared: left accent bar + light padding; no neon fills.
    def _cell(light_bg: str, light_ink: str, dark_bg: str, dark_ink: str, border: str) -> str:
        if dark:
            return (
                f"border-left: 3px solid {border}; background-color: {dark_bg}; color: {dark_ink}; "
                "font-weight: 600; padding: 0.2rem 0.5rem 0.2rem 0.45rem;"
            )
        return (
            f"border-left: 3px solid {border}; background-color: {light_bg}; color: {light_ink}; "
            "font-weight: 600; padding: 0.2rem 0.5rem 0.2rem 0.45rem;"
        )

    if label == "Buy":
        return _cell(
            "rgba(21, 128, 61, 0.12)",
            "#14532d",
            "rgba(21, 128, 61, 0.28)",
            "#e8f5ec",
            t["chart_buy"],
        )
    if label == "Sell":
        return _cell(
            "rgba(190, 18, 60, 0.10)",
            "#9f1239",
            "rgba(190, 18, 60, 0.26)",
            "#fce8ee",
            t["chart_sell"],
        )
    if label == "Sell (partial)":
        return _cell(
            "rgba(194, 65, 12, 0.12)",
            "#7c2d12",
            "rgba(194, 65, 12, 0.24)",
            "#fef3e8",
            t["chart_sell_partial"],
        )
    if label == "Exchange":
        return _cell(
            "rgba(29, 78, 216, 0.10)",
            "#1e3a8a",
            "rgba(29, 78, 216, 0.26)",
            "#e8eefc",
            t["chart_exchange"],
        )
    return _cell(
        "rgba(95, 103, 115, 0.10)",
        t["ink_soft"],
        "rgba(95, 103, 115, 0.22)",
        "#d8dce3",
        t["muted"],
    )


def _style_dataframe_buy_sell(frame: pd.DataFrame) -> pd.DataFrame | pd.io.formats.style.Styler:
    if frame.empty or "transaction_type_label" not in frame.columns:
        return frame
    n_cells = frame.shape[0] * frame.shape[1]
    cur_limit = pd.get_option("styler.render.max_elements")
    if n_cells > cur_limit:
        pd.set_option("styler.render.max_elements", n_cells)
    dark = _streamlit_theme_is_dark()
    return frame.style.map(
        lambda v, d=dark: _buy_sell_cell_style(v, dark=d),
        subset=["transaction_type_label"],
    ).hide(axis="index")


def _altair_readability(chart: alt.Chart) -> alt.Chart:
    """Shared chart typography and high-contrast axes/legends (site-wide Altair defaults)."""
    return (
        chart.configure_axis(
            labelFontSize=13,
            titleFontSize=14,
            titleFontWeight="bold",
            labelFontWeight=500,
            labelColor=THEME["chart_axis_label"],
            titleColor=THEME["chart_axis_title"],
            domainColor=THEME["chart_axis_title"],
            tickColor=THEME["chart_axis_label"],
            labelPadding=5,
            titlePadding=10,
        )
        .configure_legend(
            labelFontSize=13,
            titleFontSize=14,
            titleFontWeight="bold",
            labelFontWeight=500,
            labelColor=THEME["chart_legend_label"],
            titleColor=THEME["chart_legend_title"],
            strokeColor="rgba(12, 16, 24, 0.14)",
            fillColor="rgba(255, 252, 246, 0.98)",
            padding=12,
            cornerRadius=6,
        )
        .configure_view(
            fill=THEME["chart_view_fill"],
            stroke=THEME["chart_view_stroke"],
            strokeWidth=1,
        )
        .configure_header(labelFontSize=13, titleFontSize=14, titleFontWeight="bold")
    )

def _inject_styles(*, top_nav: bool = False) -> None:
    """Scope custom CSS to dashboard HTML components only — do not override Streamlit widgets."""
    top_nav_css = ""
    if top_nav:
        top_nav_css = """
        /* --- Fixed top navigation bar --- */
        header[data-testid="stHeader"],
        .stAppHeader {
            background: __SIDEBAR_BG__ !important;
            border-bottom: 1px solid var(--sidebar-border) !important;
            position: sticky !important;
            top: 0 !important;
            z-index: 999 !important;
        }
        .stAppHeader [data-testid="stToolbar"],
        .stAppHeader [data-testid="stToolbarActions"] {
            background: transparent !important;
        }
        .stAppHeader span,
        .stAppHeader a,
        .stAppHeader p,
        .stAppHeader button,
        .stAppHeader label {
            color: var(--sidebar-ink) !important;
        }
        .stAppHeader svg,
        .stAppHeader [data-testid="stIconMaterial"] {
            color: var(--sidebar-muted) !important;
            fill: currentColor !important;
        }
        .stAppHeader a[aria-current="page"] {
            background: rgba(255, 255, 255, 0.12) !important;
            border-radius: 8px !important;
        }
        [data-testid="stSidebar"] [data-testid="stSidebarNav"] {
            display: none !important;
        }
        /* --- Period filters pinned inside the top header bar --- */
        .st-key-period_toolbar {
            position: fixed !important;
            top: 0;
            right: 14rem;
            left: auto;
            z-index: 1000;
            height: 3.25rem;
            width: min(38rem, calc(100vw - 30rem));
            display: flex !important;
            flex-direction: column;
            justify-content: center;
            background: transparent !important;
            border: none !important;
            margin: 0 !important;
            padding: 0 0.35rem !important;
            overflow: visible !important;
        }
        /* Collapse the empty slot the toolbar leaves behind in the page flow */
        [data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] .st-key-period_toolbar),
        [data-testid="stVerticalBlock"]:has(> .st-key-period_toolbar) {
            gap: 0 !important;
        }
        .st-key-period_toolbar > div {
            width: 100%;
        }
        .stAppHeader [data-testid="stHeaderNavigation"] {
            max-width: calc(100% - 44rem);
        }
        .st-key-period_toolbar [data-testid="stHorizontalBlock"] {
            align-items: center !important;
            gap: 0.28rem !important;
            flex-wrap: nowrap !important;
        }
        .st-key-period_toolbar [data-testid="stWidgetLabel"] p,
        .st-key-period_toolbar label {
            color: var(--sidebar-ink) !important;
            font-size: 0.68rem !important;
        }
        .st-key-period_toolbar [data-baseweb="select"] > div,
        .st-key-period_toolbar .stButton > button {
            background: var(--sidebar-field) !important;
            border: 1px solid var(--sidebar-border) !important;
            border-radius: 8px !important;
            min-height: 1.85rem !important;
            max-height: 1.85rem !important;
            color: var(--sidebar-ink) !important;
        }
        .st-key-period_toolbar [data-baseweb="select"] span,
        .st-key-period_toolbar [data-baseweb="select"] div[role="combobox"],
        .st-key-period_toolbar [data-baseweb="select"] input,
        .st-key-period_toolbar [data-baseweb="select"] option,
        .st-key-period_toolbar [data-baseweb="select"] [data-testid="stMarkdownContainer"] p,
        .st-key-period_toolbar .stSelectbox p,
        .st-key-period_toolbar .stSelectbox span,
        .st-key-period_toolbar .stSelectbox div[data-baseweb="select"] * {
            color: var(--sidebar-ink) !important;
            -webkit-text-fill-color: var(--sidebar-ink) !important;
            font-size: 0.72rem !important;
        }
        .st-key-period_toolbar [data-baseweb="select"] svg {
            fill: var(--sidebar-muted) !important;
            color: var(--sidebar-muted) !important;
        }
        .st-key-period_toolbar [data-testid="stWidgetLabel"] {
            display: none !important;
        }
        .st-key-period_toolbar .stButton > button {
            background: transparent !important;
            border: 1px solid var(--sidebar-border) !important;
            color: var(--sidebar-muted) !important;
            font-size: 0.95rem !important;
            line-height: 1 !important;
            padding: 0.15rem 0.4rem !important;
            min-width: 1.85rem !important;
            max-width: 1.85rem !important;
            box-shadow: none !important;
        }
        .st-key-period_toolbar .stButton > button:hover {
            background: rgba(255, 255, 255, 0.10) !important;
            color: var(--sidebar-ink) !important;
        }
        .period-toolbar-dash {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-height: 1.85rem;
            color: var(--sidebar-muted);
            font-size: 0.78rem;
            user-select: none;
        }
        .st-key-period_toolbar [data-testid="stPills"] {
            min-width: 0;
        }
        .st-key-period_toolbar [data-testid="stPills"] button {
            min-height: 1.75rem !important;
            max-height: 1.75rem !important;
            padding: 0.12rem 0.42rem !important;
            font-size: 0.68rem !important;
            border-radius: 999px !important;
        }
        @media (max-width: 1180px) {
            .st-key-period_toolbar {
                right: 12rem;
                width: calc(100vw - 26rem);
            }
        }
        @media (max-width: 920px) {
            .st-key-period_toolbar {
                position: sticky !important;
                top: 3.25rem;
                right: auto;
                left: auto;
                width: calc(100% + 2rem);
                height: auto;
                margin: -0.85rem -1rem 0.5rem -1rem !important;
                padding: 0.35rem 1rem !important;
                background: __SIDEBAR_BG__ !important;
                border-bottom: 1px solid var(--sidebar-border) !important;
            }
        }
        """
    css = """
        <style>
        :root {
            --ink: __INK__;
            --ink-soft: __INK_SOFT__;
            --muted: __MUTED__;
            --body-secondary-strong: __BODY_SECONDARY_STRONG__;
            --line: __LINE__;
            --accent: __ACCENT__;
            --accent-deep: __ACCENT_DEEP__;
            --navy: __NAVY__;
            --shadow: __SHADOW__;
            --sidebar-ink: __SIDEBAR_INK__;
            --sidebar-muted: __SIDEBAR_MUTED__;
            --sidebar-border: __SIDEBAR_BORDER__;
            --sidebar-field: __SIDEBAR_FIELD__;
            --sidebar-field-focus: __SIDEBAR_FIELD_FOCUS__;
            --sidebar-card: __SIDEBAR_CARD__;
            --hero-ink: __HERO_INK__;
            --hero-ink-soft: __HERO_INK_SOFT__;
        }
        /* App background only — leave Streamlit widget colors to config.toml / native theme */
        .stApp {
            background:
                radial-gradient(circle at top left, rgba(198, 146, 43, 0.10), transparent 26%),
                radial-gradient(circle at top right, rgba(45, 111, 109, 0.08), transparent 24%),
                linear-gradient(180deg, #f7f2e8 0%, #f2eadf 48%, #ede3d3 100%);
        }
        section.main > div {
            padding-top: 1.25rem;
        }
        /* --- Sidebar (scoped; dark panel is intentional) --- */
        [data-testid="stSidebar"] {
            background: __SIDEBAR_BG__;
            border-right: 1px solid var(--sidebar-border);
        }
        [data-testid="stSidebar"] > div,
        [data-testid="stSidebarUserContent"] {
            background: transparent;
        }
        [data-testid="stSidebarUserContent"] {
            padding-top: 0.35rem;
            padding-bottom: 0.75rem;
        }
        [data-testid="stSidebar"] .sidebar-filters-heading,
        [data-testid="stSidebar"] .filter-section-label,
        [data-testid="stSidebar"] .sidebar-intro-title,
        [data-testid="stSidebar"] .sidebar-summary-title,
        [data-testid="stSidebar"] .sidebar-slice-bar strong,
        [data-testid="stSidebar"] .sidebar-stat-value,
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
        [data-testid="stSidebar"] [data-testid="stWidgetLabel"] p,
        [data-testid="stSidebar"] label {
            color: var(--sidebar-ink) !important;
        }
        [data-testid="stSidebar"] .sidebar-expander-caption,
        [data-testid="stSidebar"] .sidebar-intro-copy,
        [data-testid="stSidebar"] .sidebar-summary-copy,
        [data-testid="stSidebar"] .sidebar-slice-bar,
        [data-testid="stSidebar"] .sidebar-stat-label,
        [data-testid="stSidebar"] .sidebar-note {
            color: var(--sidebar-muted) !important;
        }
        [data-testid="stSidebar"] .sidebar-stat-grid-compact {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 0.4rem;
            margin-top: 0.45rem;
        }
        [data-testid="stSidebar"] .sidebar-stat-tiny {
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.06);
            border-radius: 10px;
            padding: 0.38rem 0.45rem;
        }
        [data-testid="stSidebar"] .sidebar-stat-tiny .sidebar-stat-label {
            font-size: 0.62rem !important;
            letter-spacing: 0.06em !important;
        }
        [data-testid="stSidebar"] .sidebar-stat-tiny .sidebar-stat-value {
            font-size: 0.78rem !important;
            line-height: 1.2 !important;
            margin-top: 0.15rem !important;
            word-break: break-word;
        }
        [data-testid="stSidebar"] .sidebar-slice-bar {
            display: flex;
            flex-wrap: wrap;
            align-items: baseline;
            gap: 0.35rem 0.55rem;
            background: var(--sidebar-card);
            border: 1px solid var(--sidebar-border);
            border-radius: 12px;
            padding: 0.38rem 0.5rem;
            margin: 0.35rem 0 0.15rem 0;
            font-size: 0.72rem !important;
            line-height: 1.35 !important;
        }
        [data-testid="stSidebar"] .sidebar-slice-bar .sep {
            opacity: 0.35;
            user-select: none;
        }
        [data-testid="stSidebar"] .sidebar-filters-heading {
            font-size: 0.95rem;
            font-weight: 700;
            margin: 0 0 0.15rem 0 !important;
        }
        [data-testid="stSidebar"] .filter-section-label {
            display: inline-flex;
            align-items: center;
            gap: 0.3rem;
            font-size: 0.78rem;
            font-weight: 600;
            margin: 0.35rem 0 0.08rem 0;
            line-height: 1.2;
        }
        [data-testid="stSidebar"] .filter-section-label.filter-first {
            margin-top: 0.1rem;
        }
        [data-testid="stSidebar"] .filter-has-tip {
            position: relative;
            cursor: help;
        }
        [data-testid="stSidebar"] .filter-has-tip::after {
            content: "?";
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 0.9rem;
            height: 0.9rem;
            border-radius: 50%;
            font-size: 0.58rem;
            font-weight: 700;
            line-height: 1;
            background: rgba(255, 255, 255, 0.1);
            color: var(--sidebar-muted);
            flex-shrink: 0;
        }
        [data-testid="stSidebar"] .filter-tip-popup {
            visibility: hidden;
            opacity: 0;
            pointer-events: none;
            position: absolute;
            left: 0;
            top: calc(100% + 0.25rem);
            z-index: 9999;
            width: max-content;
            max-width: 15.5rem;
            padding: 0.45rem 0.55rem;
            border-radius: 10px;
            border: 1px solid var(--sidebar-border);
            background: rgba(18, 22, 28, 0.98);
            color: var(--sidebar-ink) !important;
            font-size: 0.72rem;
            font-weight: 400;
            line-height: 1.35;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
            transition: opacity 0.12s ease;
        }
        [data-testid="stSidebar"] .filter-has-tip:hover .filter-tip-popup,
        [data-testid="stSidebar"] .filter-has-tip:focus-within .filter-tip-popup {
            visibility: visible;
            opacity: 1;
        }
        [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
            gap: 0.35rem !important;
        }
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] {
            margin-bottom: 0 !important;
        }
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
            margin-bottom: 0 !important;
        }
        [data-testid="stSidebar"] [data-baseweb="select"] > div,
        [data-testid="stSidebar"] [data-baseweb="input"] > div,
        [data-testid="stSidebar"] .stDateInput > div > div,
        [data-testid="stSidebar"] .stTextInput > div > div {
            background: var(--sidebar-field) !important;
            border: 1px solid var(--sidebar-border) !important;
            border-radius: 14px !important;
            min-height: 2.45rem;
        }
        [data-testid="stSidebar"] input,
        [data-testid="stSidebar"] textarea,
        [data-testid="stSidebar"] [data-baseweb="select"] input {
            color: var(--sidebar-ink) !important;
            -webkit-text-fill-color: var(--sidebar-ink) !important;
        }
        [data-testid="stSidebar"] input::placeholder,
        [data-testid="stSidebar"] textarea::placeholder {
            color: var(--sidebar-muted) !important;
            opacity: 1 !important;
            -webkit-text-fill-color: var(--sidebar-muted) !important;
        }
        [data-testid="stSidebar"] [data-testid="stSidebarNav"] span,
        [data-testid="stSidebar"] [data-testid="stSidebarNav"] a,
        [data-testid="stSidebar"] [data-testid="stSidebarNav"] li,
        [data-testid="stSidebar"] [data-testid="stSidebarNav"] p {
            color: var(--sidebar-ink) !important;
        }
        [data-testid="stSidebar"] [data-testid="stSidebarNav"] svg,
        [data-testid="stSidebar"] [data-testid="stSidebarNav"] [data-testid="stIconMaterial"] {
            color: var(--sidebar-muted) !important;
            fill: currentColor !important;
        }
        [data-testid="stSidebar"] [data-testid="stExpander"] summary,
        [data-testid="stSidebar"] [data-testid="stExpander"] summary span,
        [data-testid="stSidebar"] [data-testid="stExpander"] summary p {
            color: var(--sidebar-ink) !important;
        }
        [data-testid="stSidebar"] [data-baseweb="select"] span,
        [data-testid="stSidebar"] [data-baseweb="select"] div[role="combobox"] {
            color: var(--sidebar-ink) !important;
        }
        [data-testid="stSidebar"] [data-baseweb="select"] [aria-disabled="true"] span {
            color: var(--sidebar-muted) !important;
        }
        [data-testid="stSidebar"] .stMultiSelect [data-baseweb="tag"],
        [data-testid="stSidebar"] .stMultiSelect span {
            color: var(--sidebar-ink) !important;
        }
        [data-testid="stSidebar"] .stSlider label,
        [data-testid="stSidebar"] .stSlider [data-testid="stMarkdownContainer"] p {
            color: var(--sidebar-ink) !important;
        }
        /* --- Custom dashboard HTML blocks (main column) --- */
        .dashboard-shell {
            background: linear-gradient(135deg, rgba(255, 248, 236, 0.98) 0%, rgba(250, 244, 233, 0.92) 55%, rgba(238, 228, 209, 0.88) 100%);
            border: 1px solid rgba(107, 79, 47, 0.12);
            border-radius: 28px;
            padding: 1.7rem 1.7rem 1.45rem 1.7rem;
            box-shadow: var(--shadow);
            margin-bottom: 1.1rem;
            overflow: hidden;
            position: relative;
        }
        .hero-grid {
            display: grid;
            grid-template-columns: minmax(0, 1.8fr) minmax(16rem, 0.95fr);
            gap: 1rem;
            align-items: end;
        }
        .eyebrow {
            color: var(--accent);
            font-size: 0.76rem;
            font-weight: 800;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            margin-bottom: 0.45rem;
        }
        .hero-title {
            color: var(--ink);
            font-size: 2.8rem;
            line-height: 0.96;
            font-weight: 800;
            letter-spacing: -0.04em;
            margin: 0;
        }
        .hero-copy {
            color: var(--body-secondary-strong);
            font-size: 1rem;
            line-height: 1.7;
            max-width: 48rem;
            margin: 0.8rem 0 0 0;
        }
        .hero-aside {
            background: rgba(32, 52, 74, 0.94);
            color: var(--hero-ink);
            border-radius: 22px;
            padding: 1rem 1.1rem;
        }
        .hero-aside-label {
            font-size: 0.72rem;
            text-transform: uppercase;
            letter-spacing: 0.12em;
            color: var(--hero-ink-soft);
        }
        .hero-aside-value {
            font-size: 1.7rem;
            font-weight: 800;
            margin: 0.35rem 0 0.6rem 0;
        }
        .hero-meta {
            display: flex;
            flex-wrap: wrap;
            gap: 0.65rem;
            margin-top: 1rem;
        }
        .meta-pill {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            padding: 0.44rem 0.78rem;
            border-radius: 999px;
            background: rgba(32, 52, 74, 0.08);
            border: 1px solid rgba(32, 52, 74, 0.08);
            color: var(--navy);
            font-size: 0.83rem;
            font-weight: 700;
        }
        .metric-card {
            background: rgba(255, 250, 241, 0.88);
            border: 1px solid rgba(48, 58, 71, 0.10);
            border-radius: 22px;
            padding: 1rem 1.1rem;
            box-shadow: 0 14px 32px rgba(45, 35, 24, 0.06);
            min-height: 8.1rem;
        }
        .metric-card.accent {
            background: linear-gradient(180deg, rgba(166, 75, 42, 0.97) 0%, rgba(126, 53, 29, 0.96) 100%);
            color: var(--hero-ink);
            border-color: rgba(126, 53, 29, 0.40);
        }
        .metric-label {
            font-size: 0.76rem;
            font-weight: 800;
            letter-spacing: 0.09em;
            text-transform: uppercase;
            color: #3d4656;
            margin-bottom: 0.55rem;
        }
        .metric-card.accent .metric-label,
        .metric-card.accent .metric-subtle,
        .metric-card.accent .metric-value {
            color: var(--hero-ink);
        }
        .metric-card.accent .metric-label,
        .metric-card.accent .metric-subtle {
            color: var(--hero-ink-soft);
        }
        .metric-value {
            font-size: 2rem;
            line-height: 1;
            font-weight: 800;
            letter-spacing: -0.04em;
            color: var(--ink);
            margin-bottom: 0.45rem;
        }
        .metric-subtle {
            color: var(--body-secondary-strong);
            font-size: 0.92rem;
            line-height: 1.45;
        }
        .section-card {
            background: rgba(255, 250, 241, 0.92);
            border: 1px solid var(--line);
            border-radius: 24px;
            padding: 1rem 1rem 0.65rem 1rem;
            box-shadow: 0 14px 34px rgba(45, 35, 24, 0.05);
            margin-bottom: 1rem;
        }
        .section-kicker {
            color: var(--accent);
            font-size: 0.76rem;
            font-weight: 800;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            margin-bottom: 0.2rem;
        }
        .section-title {
            color: var(--ink);
            font-size: 1.2rem;
            font-weight: 800;
            margin: 0 0 0.2rem 0;
        }
        .section-copy {
            color: var(--body-secondary-strong);
            font-size: 0.94rem;
            line-height: 1.55;
            margin-bottom: 0.65rem;
        }
        /* --- Dashboard tables (shared transaction + summary styling) --- */
        .dashboard-table {
            border: 1px solid var(--line);
            border-radius: 16px;
            overflow: hidden;
            margin-bottom: 0.75rem;
            background: __TABLE_BG__;
            box-shadow: 0 8px 22px rgba(45, 35, 24, 0.04);
        }
        .dashboard-table.dt-dark {
            background: __TABLE_BG_DARK__;
            border-color: rgba(255, 255, 255, 0.10);
            box-shadow: 0 10px 28px rgba(12, 16, 24, 0.18);
        }
        .dashboard-table .dt-legend {
            display: flex;
            align-items: center;
            justify-content: flex-end;
            gap: 0.35rem;
            padding: 0.55rem 0.85rem;
            font-size: 0.72rem;
            color: var(--muted);
            border-bottom: 1px solid var(--line);
            background: __TABLE_LEGEND_BG__;
        }
        .dashboard-table.dt-dark .dt-legend {
            color: __HERO_INK_SOFT__;
            border-bottom-color: rgba(255, 255, 255, 0.08);
            background: rgba(255, 255, 255, 0.04);
        }
        .dashboard-table .dt-return-icon {
            width: 0.95rem;
            height: 0.95rem;
            color: __TABLE_RETURN_COLOR__;
            flex-shrink: 0;
        }
        .dashboard-table .dt-scroll {
            overflow-x: auto;
        }
        .dashboard-table .dt-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 0.88rem;
            line-height: 1.35;
        }
        .dashboard-table .dt-table th {
            text-align: left;
            font-size: 0.72rem;
            font-weight: 700;
            letter-spacing: 0.06em;
            text-transform: uppercase;
            color: var(--ink-soft);
            padding: 0.65rem 0.75rem;
            border-bottom: 1px solid var(--line);
            white-space: nowrap;
            background: __TABLE_HEAD_BG__;
        }
        .dashboard-table.dt-dark .dt-table th {
            color: __HERO_INK_SOFT__;
            border-bottom-color: rgba(255, 255, 255, 0.08);
            background: rgba(255, 255, 255, 0.03);
        }
        .dashboard-table .dt-table td {
            padding: 0.72rem 0.75rem;
            vertical-align: top;
            border-bottom: 1px solid var(--line);
        }
        .dashboard-table.dt-dark .dt-table td {
            border-bottom-color: rgba(255, 255, 255, 0.06);
        }
        .dashboard-table .dt-row:last-child td {
            border-bottom: none;
        }
        .dashboard-table .dt-row:hover td {
            background: __ACCENT_SOFT__;
        }
        .dashboard-table.dt-dark .dt-row:hover td {
            background: rgba(255, 255, 255, 0.04);
        }
        .dashboard-table .dt-primary {
            font-weight: 600;
            color: var(--ink);
        }
        .dashboard-table.dt-dark .dt-primary {
            color: __HERO_INK__;
        }
        .dashboard-table .dt-secondary {
            margin-top: 0.12rem;
            font-size: 0.78rem;
            color: var(--muted);
        }
        .dashboard-table.dt-dark .dt-secondary {
            color: __HERO_INK_SOFT__;
        }
        .dashboard-table .dt-plain {
            color: var(--ink);
            font-weight: 500;
        }
        .dashboard-table.dt-dark .dt-plain {
            color: __HERO_INK__;
        }
        .dashboard-table .dt-stock-wrap,
        .dashboard-table .dt-member-wrap {
            display: flex;
            align-items: flex-start;
            gap: 0.55rem;
            min-width: 10rem;
        }
        .dashboard-table .dt-stock-icon {
            width: 1.05rem;
            height: 1.05rem;
            margin-top: 0.12rem;
            flex-shrink: 0;
            color: __TEAL__;
        }
        .dashboard-table.dt-dark .dt-stock-icon {
            color: __GOLD__;
        }
        .dashboard-table .dt-avatar {
            width: 2rem;
            height: 2rem;
            border-radius: 999px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-size: 0.68rem;
            font-weight: 800;
            color: #fff;
            flex-shrink: 0;
            letter-spacing: 0.02em;
            box-shadow: 0 2px 8px rgba(32, 52, 74, 0.18);
        }
        .dashboard-table .dt-txn-buy { color: __CHART_BUY__; }
        .dashboard-table .dt-txn-sell,
        .dashboard-table .dt-txn-sell-partial { color: __CHART_SELL_PARTIAL__; }
        .dashboard-table .dt-txn-exchange { color: __CHART_EXCHANGE__; }
        .dashboard-table .dt-txn-unknown { color: var(--muted); }
        .dashboard-table .dt-ticker {
            white-space: nowrap;
            font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
            font-size: 0.84rem;
            letter-spacing: 0.02em;
        }
        .dashboard-table .dt-date {
            white-space: nowrap;
            color: var(--ink-soft);
        }
        .dashboard-table.dt-dark .dt-date {
            color: __HERO_INK__;
        }
        .dashboard-table .dt-desc {
            max-width: 16rem;
            color: var(--muted);
            font-size: 0.8rem;
        }
        .dashboard-table.dt-dark .dt-desc {
            color: __HERO_INK_SOFT__;
        }
        .dashboard-table .dt-return {
            white-space: nowrap;
            min-width: 4.5rem;
        }
        .dashboard-table .dt-return-wrap {
            display: inline-flex;
            align-items: center;
            gap: 0.25rem;
            font-size: 0.78rem;
            font-weight: 600;
        }
        .dashboard-table .dt-return-up { color: __CHART_BUY__; }
        .dashboard-table .dt-return-down { color: __CHART_SELL__; }
        .dashboard-table .dt-return-neutral { color: var(--muted); }
        .dashboard-table.dt-dark .dt-return-neutral { color: __HERO_INK_SOFT__; }
        .dashboard-table .dt-th-return { width: 4.5rem; }
        /* --- Color-coded summary cells --- */
        .dashboard-table .dt-cell-buy .dt-plain {
            color: __CHART_BUY__;
            font-weight: 700;
        }
        .dashboard-table .dt-cell-sell .dt-plain {
            color: __CHART_SELL__;
            font-weight: 700;
        }
        .dashboard-table .dt-cell-call .dt-plain {
            color: __CHART_EXCHANGE__;
            font-weight: 700;
        }
        .dashboard-table .dt-cell-put .dt-plain {
            color: __CHART_SELL_PARTIAL__;
            font-weight: 700;
        }
        .dashboard-table .dt-cell-trades .dt-plain {
            color: var(--navy);
            font-weight: 700;
        }
        .dashboard-table .dt-cell-range .dt-plain {
            color: var(--accent-deep);
            font-weight: 600;
        }
        .dashboard-table .dt-cell-accent .dt-plain,
        .dashboard-table .dt-cell-accent .dt-nav-link {
            color: var(--accent);
            font-weight: 700;
        }
        .dashboard-table .dt-cell-pct .dt-plain {
            color: __TEAL__;
            font-weight: 600;
        }
        .dashboard-table .dt-cell-trades .dt-nav-link {
            color: var(--navy);
            font-weight: 700;
            border-bottom-color: rgba(32, 52, 74, 0.35);
        }
        .dashboard-table .dt-cell-buy .dt-nav-link { color: __CHART_BUY__; font-weight: 700; }
        .dashboard-table .dt-cell-sell .dt-nav-link { color: __CHART_SELL__; font-weight: 700; }
        .dashboard-table .dt-cell-range .dt-nav-link {
            color: var(--accent-deep);
            font-weight: 600;
        }
        .dashboard-table.dt-dark .dt-cell-buy .dt-plain { color: #4ade80; }
        .dashboard-table.dt-dark .dt-cell-sell .dt-plain { color: #fb7185; }
        .dashboard-table.dt-dark .dt-cell-call .dt-plain { color: #60a5fa; }
        .dashboard-table.dt-dark .dt-cell-put .dt-plain { color: #fb923c; }
        .dashboard-table.dt-dark .dt-cell-trades .dt-plain { color: #e2e8f0; }
        .dashboard-table.dt-dark .dt-cell-range .dt-plain { color: __GOLD__; }
        .dashboard-table.dt-dark .dt-cell-accent .dt-plain,
        .dashboard-table.dt-dark .dt-cell-accent .dt-nav-link { color: __GOLD__; }
        .dashboard-table.dt-dark .dt-cell-pct .dt-plain { color: #5eead4; }
        .dashboard-table.dt-dark .dt-cell-trades .dt-nav-link { color: #e2e8f0; }
        /* Navigation links inside tables */
        .dashboard-table .dt-nav-link {
            color: inherit;
            text-decoration: none;
            border-bottom: 1px dashed var(--muted);
            transition: border-color 0.15s, color 0.15s;
        }
        .dashboard-table .dt-nav-link:hover {
            color: var(--accent);
            border-bottom-color: var(--accent);
            border-bottom-style: solid;
        }
        .dashboard-table.dt-dark .dt-nav-link:hover {
            color: __GOLD__;
            border-bottom-color: __GOLD__;
        }
        /* Don't clip Streamlit chart/dataframe hover toolbars */
        div[data-testid="stDataFrame"] {
            overflow: visible;
        }
        @media (min-width: 1440px) {
            section.main div.block-container {
                max-width: min(calc(100vw - 17.5rem), 1680px) !important;
                margin-left: auto !important;
                margin-right: auto !important;
            }
        }
        @media (max-width: 980px) {
            .hero-grid {
                grid-template-columns: 1fr;
            }
            .hero-title {
                font-size: 2.2rem;
            }
        }
        __TOP_NAV_CSS__
        </style>
    """
    css = (
        css.replace("__TOP_NAV_CSS__", top_nav_css)
        .replace("__INK__", THEME["ink"])
        .replace("__INK_SOFT__", THEME["ink_soft"])
        .replace("__MUTED__", THEME["muted"])
        .replace("__BODY_SECONDARY_STRONG__", THEME["ui_body_secondary"])
        .replace("__LINE__", THEME["line"])
        .replace("__ACCENT__", THEME["accent"])
        .replace("__ACCENT_DEEP__", THEME["accent_deep"])
        .replace("__NAVY__", THEME["navy"])
        .replace("__SHADOW__", THEME["shadow"])
        .replace("__SIDEBAR_BG__", THEME["sidebar_bg"])
        .replace("__SIDEBAR_INK__", THEME["sidebar_ink"])
        .replace("__SIDEBAR_MUTED__", THEME["sidebar_muted"])
        .replace("__SIDEBAR_BORDER__", THEME["sidebar_border"])
        .replace("__SIDEBAR_FIELD__", THEME["sidebar_field"])
        .replace("__SIDEBAR_FIELD_FOCUS__", THEME["sidebar_field_focus"])
        .replace("__SIDEBAR_CARD__", THEME["sidebar_card"])
        .replace("__HERO_INK__", THEME["hero_ink"])
        .replace("__HERO_INK_SOFT__", THEME["hero_ink_soft"])
        .replace("__CHART_BUY__", THEME["chart_buy"])
        .replace("__CHART_SELL__", THEME["chart_sell"])
        .replace("__CHART_SELL_PARTIAL__", THEME["chart_sell_partial"])
        .replace("__CHART_EXCHANGE__", THEME["chart_exchange"])
        .replace("__TABLE_BG__", THEME["bg_panel"])
        .replace("__TABLE_BG_DARK__", "rgba(32, 52, 74, 0.94)")
        .replace("__TABLE_HEAD_BG__", "rgba(255, 250, 241, 0.55)")
        .replace("__TABLE_LEGEND_BG__", "rgba(255, 250, 241, 0.72)")
        .replace("__TABLE_RETURN_COLOR__", THEME["teal"])
        .replace("__ACCENT_SOFT__", THEME["accent_soft"])
        .replace("__TEAL__", THEME["teal"])
        .replace("__GOLD__", THEME["gold"])
    )
    st.markdown(css, unsafe_allow_html=True)
