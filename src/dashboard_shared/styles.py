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
            "rgba(45, 111, 109, 0.12)",
            "#153d3b",
            "rgba(45, 111, 109, 0.26)",
            "#e4f2f0",
            t["teal"],
        )
    if label == "Sell":
        return _cell(
            t["accent_soft"],
            t["accent_deep"],
            "rgba(166, 75, 42, 0.26)",
            "#f8ece8",
            t["accent"],
        )
    if label == "Sell (partial)":
        return _cell(
            "rgba(198, 146, 43, 0.14)",
            "#5a4518",
            "rgba(198, 146, 43, 0.22)",
            "#f7efd8",
            t["gold"],
        )
    if label == "Exchange":
        return _cell(
            "rgba(32, 52, 74, 0.09)",
            t["navy"],
            "rgba(32, 52, 74, 0.32)",
            "#e8edf4",
            "#2d4a6e",
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

def _inject_styles() -> None:
    css = """
        <style>
        :root {
            --bg: __BG__;
            --bg-panel: __BG_PANEL__;
            --bg-strong: __BG_PANEL_STRONG__;
            --ink: __INK__;
            --ink-soft: __INK_SOFT__;
            --muted: __MUTED__;
            --caption-ink: __CAPTION_INK__;
            --body-secondary-strong: __BODY_SECONDARY_STRONG__;
            --line: __LINE__;
            --accent: __ACCENT__;
            --accent-deep: __ACCENT_DEEP__;
            --accent-soft: __ACCENT_SOFT__;
            --navy: __NAVY__;
            --teal: __TEAL__;
            --gold: __GOLD__;
            --shadow: __SHADOW__;
            --sidebar-ink: __SIDEBAR_INK__;
            --sidebar-muted: __SIDEBAR_MUTED__;
            --sidebar-border: __SIDEBAR_BORDER__;
            --sidebar-field: __SIDEBAR_FIELD__;
            --sidebar-field-focus: __SIDEBAR_FIELD_FOCUS__;
            --sidebar-card: __SIDEBAR_CARD__;
            --button-ink: __BUTTON_INK__;
        }
        .stApp {
            background:
                radial-gradient(circle at top left, rgba(198, 146, 43, 0.14), transparent 26%),
                radial-gradient(circle at top right, rgba(45, 111, 109, 0.12), transparent 24%),
                linear-gradient(180deg, #f7f2e8 0%, #f2eadf 48%, #ede3d3 100%);
            color: var(--ink);
        }
        .stApp,
        .stApp p,
        .stApp li,
        .stApp label,
        .stApp span,
        .stApp h1,
        .stApp h2,
        .stApp h3,
        .stApp h4,
        .stApp h5,
        .stApp h6,
        [data-testid="stMarkdownContainer"],
        [data-testid="stCaptionContainer"],
        [data-testid="stHeader"] {
            color: var(--ink);
        }
        /* Main column: Streamlit captions default to low-contrast grey — force readable body text */
        [data-testid="stMain"] [data-testid="stCaptionContainer"] p,
        [data-testid="stMain"] [data-testid="stCaptionContainer"] div,
        [data-testid="stMain"] [data-testid="stCaptionContainer"] span,
        [data-testid="stMain"] [data-testid="stCaptionContainer"] label {
            color: var(--caption-ink) !important;
            opacity: 1 !important;
            font-size: 0.94rem !important;
            line-height: 1.58 !important;
            font-weight: 500 !important;
        }
        [data-testid="stMain"] h1,
        [data-testid="stMain"] h2,
        [data-testid="stMain"] h3 {
            color: var(--ink) !important;
        }
        [data-testid="stMain"] [data-testid="stMarkdownContainer"] p,
        [data-testid="stMain"] [data-testid="stMarkdownContainer"] li {
            color: var(--ink);
        }
        section.main > div {
            padding-top: 1.25rem;
        }
        [data-testid="stSidebar"] {
            background: __SIDEBAR_BG__;
            border-right: 1px solid var(--sidebar-border);
        }
        [data-testid="stSidebar"] > div {
            background: transparent;
        }
        [data-testid="stSidebarUserContent"] {
            padding-top: 0.35rem;
            padding-bottom: 0.75rem;
        }
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
        [data-testid="stSidebar"] [data-testid="stCaptionContainer"] p,
        [data-testid="stSidebar"] [data-testid="stWidgetLabel"] p,
        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] span,
        [data-testid="stSidebar"] div,
        [data-testid="stSidebar"] small {
            color: var(--sidebar-ink);
        }
        [data-testid="stSidebar"] h1,
        [data-testid="stSidebar"] h2,
        [data-testid="stSidebar"] h3 {
            color: var(--sidebar-ink) !important;
        }
        [data-testid="stSidebar"] .stMarkdown a {
            color: #ffd9bf;
        }
        [data-testid="stSidebar"] .sidebar-intro,
        [data-testid="stSidebar"] .sidebar-summary {
            background: var(--sidebar-card);
            border: 1px solid var(--sidebar-border);
            border-radius: 22px;
            padding: 1rem 1rem 0.95rem 1rem;
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.03);
            margin-bottom: 0.95rem;
        }
        [data-testid="stSidebar"] .sidebar-filters-heading {
            color: var(--sidebar-ink) !important;
            font-size: 0.95rem;
            font-weight: 800;
            letter-spacing: -0.02em;
            margin: 0 0 0.35rem 0;
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
        [data-testid="stSidebar"] .sidebar-expander-caption {
            color: var(--sidebar-muted) !important;
            font-size: 0.72rem !important;
            line-height: 1.35 !important;
            margin: 0 0 0.35rem 0 !important;
        }
        [data-testid="stSidebar"] .sidebar-slice-bar {
            display: flex;
            flex-wrap: wrap;
            align-items: baseline;
            gap: 0.35rem 0.55rem;
            background: var(--sidebar-card);
            border: 1px solid var(--sidebar-border);
            border-radius: 12px;
            padding: 0.45rem 0.55rem;
            margin: 0.5rem 0 0.35rem 0;
            color: var(--sidebar-muted) !important;
            font-size: 0.72rem !important;
            line-height: 1.35 !important;
        }
        [data-testid="stSidebar"] .sidebar-slice-bar strong {
            color: var(--sidebar-ink) !important;
            font-weight: 800;
        }
        [data-testid="stSidebar"] .sidebar-slice-bar .sep {
            opacity: 0.35;
            user-select: none;
        }
        [data-testid="stSidebar"] .sidebar-intro-title,
        [data-testid="stSidebar"] .sidebar-summary-title {
            color: var(--sidebar-ink) !important;
            font-size: 1.02rem;
            font-weight: 800;
            letter-spacing: -0.02em;
            margin: 0;
        }
        [data-testid="stSidebar"] .sidebar-intro-copy,
        [data-testid="stSidebar"] .sidebar-summary-copy,
        [data-testid="stSidebar"] .filter-section-copy {
            color: var(--sidebar-muted) !important;
            font-size: 0.86rem;
            line-height: 1.55;
            margin: 0.28rem 0 0 0;
        }
        [data-testid="stSidebar"] .sidebar-stat-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.65rem;
            margin-top: 0.9rem;
        }
        [data-testid="stSidebar"] .sidebar-stat {
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.06);
            border-radius: 16px;
            padding: 0.75rem 0.8rem;
        }
        [data-testid="stSidebar"] .sidebar-stat-label {
            color: var(--sidebar-muted) !important;
            font-size: 0.72rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            font-weight: 700;
        }
        [data-testid="stSidebar"] .sidebar-stat-value {
            color: var(--sidebar-ink) !important;
            font-size: 1.15rem;
            line-height: 1.1;
            font-weight: 800;
            margin-top: 0.28rem;
        }
        [data-testid="stSidebar"] .filter-section-label {
            color: var(--sidebar-ink) !important;
            font-size: 0.82rem;
            font-weight: 800;
            letter-spacing: -0.01em;
            margin: 0.38rem 0 0.08rem 0;
        }
        [data-testid="stSidebar"] .filter-section-label.filter-first {
            margin-top: 0.15rem;
        }
        [data-testid="stSidebar"] .filter-section-copy {
            margin-bottom: 0.2rem;
            font-size: 0.78rem !important;
            line-height: 1.35 !important;
        }
        [data-testid="stSidebar"] .stMultiSelect [data-baseweb="select"] > div {
            min-height: 2.85rem !important;
            max-height: 10rem !important;
            overflow-y: auto !important;
            overflow-x: hidden !important;
            align-items: center !important;
            padding-top: 0.35rem !important;
            padding-bottom: 0.35rem !important;
        }
        [data-testid="stSidebar"] .stMultiSelect [data-baseweb="select"] [data-baseweb="value"] {
            line-height: 1.35 !important;
            min-height: 1.35em !important;
        }
        [data-testid="stSidebar"] .stMultiSelect [data-baseweb="select"] [data-baseweb="tag"] {
            margin: 2px 4px 2px 0 !important;
        }
        [data-testid="stSidebar"] [data-baseweb="select"] > div,
        [data-testid="stSidebar"] [data-baseweb="input"] > div,
        [data-testid="stSidebar"] .stDateInput > div > div,
        [data-testid="stSidebar"] .stTextInput > div > div {
            background: var(--sidebar-field) !important;
            border: 1px solid var(--sidebar-border) !important;
            border-radius: 16px !important;
            min-height: 3rem;
            box-shadow: none !important;
            transition: border-color 160ms ease, background 160ms ease, transform 160ms ease;
        }
        [data-testid="stSidebar"] [data-baseweb="select"] > div:hover,
        [data-testid="stSidebar"] [data-baseweb="input"] > div:hover,
        [data-testid="stSidebar"] .stDateInput > div > div:hover,
        [data-testid="stSidebar"] .stTextInput > div > div:hover {
            border-color: rgba(255, 255, 255, 0.2) !important;
            background: var(--sidebar-field-focus) !important;
        }
        [data-testid="stSidebar"] input,
        [data-testid="stSidebar"] textarea,
        [data-testid="stSidebar"] [data-baseweb="select"] input {
            color: var(--sidebar-ink) !important;
            -webkit-text-fill-color: var(--sidebar-ink) !important;
        }
        [data-testid="stSidebar"] input::placeholder,
        [data-testid="stSidebar"] textarea::placeholder {
            color: rgba(241, 232, 220, 0.45) !important;
            -webkit-text-fill-color: rgba(241, 232, 220, 0.45) !important;
        }
        [data-testid="stSidebar"] [data-baseweb="tag"] {
            background: rgba(166, 75, 42, 0.96) !important;
            border-radius: 12px !important;
            border: 1px solid rgba(255, 214, 189, 0.12) !important;
            color: var(--button-ink) !important;
        }
        [data-testid="stSidebar"] [data-baseweb="tag"] span,
        [data-testid="stSidebar"] [data-baseweb="tag"] svg,
        [data-testid="stSidebar"] button svg,
        [data-testid="stSidebar"] [data-baseweb="select"] svg {
            color: var(--sidebar-ink) !important;
            fill: currentColor !important;
        }
        [data-testid="stSidebar"] .stSlider [data-baseweb="slider"] {
            padding-left: 0.15rem;
            padding-right: 0.15rem;
        }
        [data-testid="stSidebar"] .stSlider [data-baseweb="slider"] > div[data-testid="stTickBar"] {
            background: rgba(255, 255, 255, 0.12);
        }
        [data-testid="stSidebar"] .stSlider [role="slider"] {
            background: #ffd8c0 !important;
            border: 2px solid rgba(126, 53, 29, 0.72) !important;
            box-shadow: 0 0 0 4px rgba(166, 75, 42, 0.18);
        }
        [data-testid="stSidebar"] .stSlider [data-baseweb="slider"] > div > div {
            background: linear-gradient(90deg, #d9774d 0%, #a64b2a 100%);
        }
        [data-testid="stSidebar"] .stDateInput,
        [data-testid="stSidebar"] .stTextInput,
        [data-testid="stSidebar"] .stMultiSelect,
        [data-testid="stSidebar"] .stSelectbox,
        [data-testid="stSidebar"] .stSlider {
            margin-bottom: 0.42rem;
        }
        [data-testid="stSidebar"] [data-testid="stExpander"] {
            margin-bottom: 0.35rem;
        }
        [data-testid="stSidebar"] .sidebar-note {
            color: var(--sidebar-muted) !important;
            margin-top: 0.2rem;
            margin-bottom: 0.35rem;
            font-size: 0.72rem !important;
            line-height: 1.35 !important;
        }
        .stButton > button,
        .stDownloadButton > button,
        button[kind="secondary"] {
            background: linear-gradient(180deg, rgba(166, 75, 42, 0.98) 0%, rgba(126, 53, 29, 0.98) 100%);
            color: var(--button-ink) !important;
            border: 1px solid rgba(126, 53, 29, 0.54) !important;
            border-radius: 999px !important;
            padding: 0.62rem 1rem !important;
            font-weight: 700 !important;
            box-shadow: 0 12px 24px rgba(126, 53, 29, 0.16);
        }
        .stButton > button:hover,
        .stDownloadButton > button:hover,
        button[kind="secondary"]:hover {
            transform: translateY(-1px);
            border-color: rgba(126, 53, 29, 0.72) !important;
            filter: brightness(1.04);
        }
        .stButton > button:focus:not(:focus-visible),
        .stDownloadButton > button:focus:not(:focus-visible),
        button[kind="secondary"]:focus:not(:focus-visible) {
            box-shadow: 0 12px 24px rgba(126, 53, 29, 0.16);
        }
        .stButton > button:focus-visible,
        .stDownloadButton > button:focus-visible,
        button[kind="secondary"]:focus-visible {
            box-shadow: 0 0 0 3px rgba(166, 75, 42, 0.22), 0 12px 24px rgba(126, 53, 29, 0.16) !important;
            outline: none;
        }
        .dashboard-shell {
            background:
                linear-gradient(135deg, rgba(255, 248, 236, 0.98) 0%, rgba(250, 244, 233, 0.92) 55%, rgba(238, 228, 209, 0.88) 100%);
            border: 1px solid rgba(107, 79, 47, 0.12);
            border-radius: 28px;
            padding: 1.7rem 1.7rem 1.45rem 1.7rem;
            box-shadow: var(--shadow);
            margin-bottom: 1.1rem;
            overflow: hidden;
            position: relative;
        }
        .dashboard-shell::after {
            content: "";
            position: absolute;
            inset: auto -3rem -3rem auto;
            width: 14rem;
            height: 14rem;
            background: radial-gradient(circle, rgba(45, 111, 109, 0.16) 0%, rgba(45, 111, 109, 0) 68%);
            pointer-events: none;
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
            font-weight: 450;
        }
        .hero-aside {
            background: rgba(32, 52, 74, 0.94);
            color: __HERO_INK__;
            border-radius: 22px;
            padding: 1rem 1.1rem;
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.05);
        }
        .hero-aside-label {
            font-size: 0.72rem;
            text-transform: uppercase;
            letter-spacing: 0.12em;
            color: __HERO_INK_SOFT__;
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
            color: __HERO_INK__;
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
        .metric-card.accent .metric-subtle {
            color: __HERO_INK_SOFT__;
        }
        .metric-value {
            font-size: 2rem;
            line-height: 1;
            font-weight: 800;
            letter-spacing: -0.04em;
            color: var(--ink);
            margin-bottom: 0.45rem;
        }
        .metric-card.accent .metric-value {
            color: __HERO_INK__;
        }
        .metric-subtle {
            color: var(--body-secondary-strong);
            font-size: 0.92rem;
            line-height: 1.45;
            font-weight: 450;
        }
        .section-card {
            background: var(--bg-panel);
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
            font-weight: 450;
            line-height: 1.55;
            margin-bottom: 0.65rem;
        }
        div[data-testid="stDataFrame"] {
            border: 1px solid rgba(48, 58, 71, 0.12);
            border-radius: 18px;
            overflow: hidden;
            background: rgba(255, 250, 241, 0.72);
        }
        button[kind="secondary"] {
            border-radius: 999px;
            border: 1px solid rgba(32, 52, 74, 0.12);
        }
        .stTabs [data-baseweb="tab-list"] {
            gap: 0.45rem;
            margin-bottom: 0.65rem;
            padding: 0.2rem 0;
            flex-wrap: wrap;
        }
        .stTabs [data-baseweb="tab"] {
            background: rgba(255, 250, 241, 0.72);
            border: 1px solid rgba(48, 58, 71, 0.10);
            border-radius: 999px;
            padding: 0.38rem 1.05rem;
            height: auto;
            min-height: 2.35rem;
            color: var(--ink);
            transition: background 0.15s ease, border-color 0.15s ease, color 0.15s ease;
        }
        .stTabs [data-baseweb="tab"] * {
            color: var(--ink);
        }
        .stTabs [data-baseweb="tab"]:hover {
            border-color: rgba(166, 75, 42, 0.28);
            background: rgba(255, 250, 241, 0.95);
        }
        .stTabs [data-baseweb="tab"]:focus-visible {
            outline: 2px solid var(--accent);
            outline-offset: 2px;
        }
        .stTabs [aria-selected="true"] {
            background: rgba(166, 75, 42, 0.14);
            color: var(--accent-deep);
            border-color: rgba(166, 75, 42, 0.35);
            font-weight: 700;
        }
        .stTabs [aria-selected="true"] * {
            color: var(--accent-deep);
        }
        .stAlert {
            color: var(--ink);
        }
        h2, h3 {
            color: var(--ink);
        }
        /* Large / ultrawide: cap line length, add breathing room, keep charts readable */
        @media (min-width: 1280px) {
            section.main div.block-container {
                padding-left: clamp(1.25rem, 2.2vw, 3.5rem) !important;
                padding-right: clamp(1.25rem, 2.2vw, 3.5rem) !important;
            }
        }
        @media (min-width: 1440px) {
            section.main div.block-container {
                max-width: min(calc(100vw - 17.5rem), 1680px) !important;
                margin-left: auto !important;
                margin-right: auto !important;
            }
            .dashboard-shell {
                padding: 1.95rem 2rem 1.65rem 2rem;
            }
            .hero-title {
                font-size: 3rem;
            }
            .section-title {
                font-size: 1.28rem;
            }
            .metric-value {
                font-size: 2.1rem;
            }
        }
        @media (min-width: 1800px) {
            section.main div.block-container {
                max-width: min(calc(100vw - 18.5rem), 1980px) !important;
            }
            .dashboard-shell {
                padding: 2.1rem 2.25rem 1.75rem 2.25rem;
            }
            .hero-title {
                font-size: 3.25rem;
            }
            .hero-copy {
                font-size: 1.05rem;
                max-width: 52rem;
            }
            .section-title {
                font-size: 1.38rem;
            }
            .section-copy {
                font-size: 1rem;
            }
            .metric-value {
                font-size: 2.2rem;
            }
            [data-testid="stSidebar"] {
                min-width: 19.5rem;
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
        @media (prefers-reduced-motion: reduce) {
            .stTabs [data-baseweb="tab"],
            .stButton > button,
            .stDownloadButton > button,
            button[kind="secondary"] {
                transition: none;
            }
            .stButton > button:hover,
            .stDownloadButton > button:hover,
            button[kind="secondary"]:hover {
                transform: none;
            }
        }
        </style>
    """
    css = (
        css.replace("__BG__", THEME["bg"])
        .replace("__BG_PANEL__", THEME["bg_panel"])
        .replace("__BG_PANEL_STRONG__", THEME["bg_panel_strong"])
        .replace("__INK__", THEME["ink"])
        .replace("__INK_SOFT__", THEME["ink_soft"])
        .replace("__MUTED__", THEME["muted"])
        .replace("__CAPTION_INK__", THEME["ui_caption"])
        .replace("__BODY_SECONDARY_STRONG__", THEME["ui_body_secondary"])
        .replace("__LINE__", THEME["line"])
        .replace("__ACCENT__", THEME["accent"])
        .replace("__ACCENT_DEEP__", THEME["accent_deep"])
        .replace("__ACCENT_SOFT__", THEME["accent_soft"])
        .replace("__NAVY__", THEME["navy"])
        .replace("__TEAL__", THEME["teal"])
        .replace("__GOLD__", THEME["gold"])
        .replace("__SHADOW__", THEME["shadow"])
        .replace("__SIDEBAR_BG__", THEME["sidebar_bg"])
        .replace("__SIDEBAR_INK__", THEME["sidebar_ink"])
        .replace("__SIDEBAR_MUTED__", THEME["sidebar_muted"])
        .replace("__SIDEBAR_BORDER__", THEME["sidebar_border"])
        .replace("__SIDEBAR_FIELD__", THEME["sidebar_field"])
        .replace("__SIDEBAR_FIELD_FOCUS__", THEME["sidebar_field_focus"])
        .replace("__SIDEBAR_CARD__", THEME["sidebar_card"])
        .replace("__BUTTON_INK__", THEME["button_ink"])
        .replace("__HERO_INK__", THEME["hero_ink"])
        .replace("__HERO_INK_SOFT__", THEME["hero_ink_soft"])
    )
    st.markdown(
        css,
        unsafe_allow_html=True,
    )
