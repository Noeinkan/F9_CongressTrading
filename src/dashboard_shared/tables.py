"""Standard dashboard table builder — shared shell, theme, and color roles."""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from typing import Literal
from urllib.parse import quote

import pandas as pd
import streamlit as st

from .styles import _streamlit_theme_is_dark

TableTheme = Literal["light", "dark", "auto"]
TableVariant = Literal["summary", "transactions"]
ColorRole = Literal[
    "buy",
    "sell",
    "call",
    "put",
    "trades",
    "range",
    "pct",
    "accent",
    "neutral",
]

_DATE_COLUMNS = frozenset(
    {
        "transaction_date",
        "filing_date",
        "first_trade",
        "last_trade",
        "date_from",
        "date_to",
    }
)

# Default column-name → semantic color role (override per table via TableConfig.color_columns).
DEFAULT_COLOR_COLUMNS: dict[str, ColorRole] = {
    "buy": "buy",
    "buys": "buy",
    "purchases": "buy",
    "sell": "sell",
    "sells": "sell",
    "sales": "sell",
    "call": "call",
    "calls": "call",
    "put": "put",
    "puts": "put",
    "trades": "trades",
    "transactions": "trades",
    "trade_count": "trades",
    "total_trades": "trades",
    "disclosed_range": "range",
    "amount_range_raw": "range",
    "relevant_trades": "accent",
    "relevance_pct": "pct",
}


@dataclass
class TableConfig:
    """Configurable dashboard table — tweak columns, links, colors, and theme per use case."""

    variant: TableVariant = "summary"
    theme: TableTheme = "light"
    columns: list[str] | None = None
    headers: dict[str, str] = field(default_factory=dict)
    link_columns: dict[str, dict[str, object]] = field(default_factory=dict)
    color_columns: dict[str, ColorRole] = field(default_factory=dict)
    legend: str | None = None
    empty_message: str = "No rows to display."


def _escape(text: object) -> str:
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return ""
    return html.escape(str(text))


def resolve_table_theme(theme: TableTheme) -> str:
    """Return CSS class for table shell. Default light matches the warm dashboard shell."""
    if theme == "auto":
        return "dt-dark" if _streamlit_theme_is_dark() else "dt-light"
    return "dt-dark" if theme == "dark" else "dt-light"


def resolve_color_class(column: str, color_columns: dict[str, ColorRole]) -> str:
    role = color_columns.get(column) or DEFAULT_COLOR_COLUMNS.get(column.lower())
    return f"dt-cell-{role}" if role else ""


def _format_table_date(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"
    try:
        return pd.Timestamp(value).strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return "—"


def format_cell(column: str, value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"
    if column in _DATE_COLUMNS:
        return _format_table_date(value)
    if isinstance(value, float) and column not in (
        "spike_ratio",
        "recent_per_month",
        "prior_per_month",
        "call_put_ratio",
        "relevance_pct",
    ):
        if value == int(value):
            return f"{int(value):,}"
        return f"{value:,.2f}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def nav_link_params(text: str, page: str, params: dict[str, str]) -> str:
    slug = page.lower().replace(" ", "_")
    qs = "&".join(f"{quote(k, safe='')}={quote(v, safe='')}" for k, v in params.items() if v)
    return f'<a class="dt-nav-link" href="/{slug}?{qs}" target="_parent">{text}</a>'


def table_shell(*, body: str, legend: str | None, variant: str, theme: TableTheme = "light") -> str:
    theme_cls = resolve_table_theme(theme)
    legend_html = f'<div class="dt-legend">{legend}</div>' if legend else ""
    return (
        f'<div class="dashboard-table {theme_cls} {variant}">'
        f"{legend_html}"
        f'<div class="dt-scroll"><table class="dt-table">{body}</table></div>'
        f"</div>"
    )


def _link_params_for_row(
    column: str,
    row: pd.Series,
    frame: pd.DataFrame,
    link_columns: dict[str, dict[str, object]],
) -> dict[str, str]:
    spec = link_columns[column]
    page = str(spec.get("page") or "Members")
    query = spec.get("query") or {}
    params: dict[str, str] = {}
    for param_name, source in query.items():
        if isinstance(source, str) and source in frame.columns:
            params[str(param_name)] = str(row.get(source) or "")
        else:
            params[str(param_name)] = str(source)
    return params


def build_table_html(frame: pd.DataFrame, config: TableConfig | None = None) -> str:
    """Build a standard summary table from a DataFrame and TableConfig."""
    cfg = config or TableConfig()
    if frame.empty:
        return ""
    cols = cfg.columns or list(frame.columns)
    cols = [c for c in cols if c in frame.columns]
    if not cols:
        return ""
    head = "".join(
        f"<th>{_escape(cfg.headers.get(c, c.replace('_', ' ').title()))}</th>" for c in cols
    )
    body_rows: list[str] = []
    for _, row in frame.iterrows():
        cells: list[str] = []
        for c in cols:
            role_cls = resolve_color_class(c, cfg.color_columns)
            td_class = f"dt-cell {role_cls}" if role_cls else "dt-cell"
            cell_text = format_cell(c, row.get(c))
            if c in cfg.link_columns:
                params = _link_params_for_row(c, row, frame, cfg.link_columns)
                page = str(cfg.link_columns[c].get("page") or "Members")
                inner = nav_link_params(_escape(cell_text), page, params)
            else:
                inner = f'<span class="dt-plain">{_escape(cell_text)}</span>'
            cells.append(f'<td class="{td_class}">{inner}</td>')
        body_rows.append(f'<tr class="dt-row">{"".join(cells)}</tr>')
    body = f"<thead><tr>{head}</tr></thead><tbody>{''.join(body_rows)}</tbody>"
    return table_shell(body=body, legend=cfg.legend, variant=f"dt-{cfg.variant}", theme=cfg.theme)


def render_table(frame: pd.DataFrame, config: TableConfig | None = None) -> None:
    """Render a standard table in Streamlit."""
    cfg = config or TableConfig()
    if frame.empty:
        st.info(cfg.empty_message)
        return
    html_out = build_table_html(frame, cfg)
    if not html_out:
        st.info(cfg.empty_message)
        return
    st.html(html_out)
