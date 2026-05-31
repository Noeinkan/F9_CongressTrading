from __future__ import annotations

import html
import re
from datetime import date

import pandas as pd
import streamlit as st

from .constants import THEME
from .data import merge_polygon_pnl_cached_columns
from .formatting import format_disclosed_range
from .tables import (
    TableConfig,
    build_table_html,
    nav_link_params,
    render_table,
    table_shell,
)


def _escape(text: object) -> str:
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return ""
    return html.escape(str(text))


def _render_table_html(html_out: str) -> None:
    """Render table HTML without markdown (indented tags become code blocks in st.markdown)."""
    st.html(html_out)


_SORT_COLUMNS = {
    "Traded": "transaction_date",
    "Filed": "filing_date",
    "Ticker": "ticker",
    "Stock": "issuer_name",
    "Politician": "member",
    "Transaction": "transaction_type",
}


def asset_type_feed_label(asset_type: object, asset_name: object = "") -> str:
    raw = "" if asset_type is None or (isinstance(asset_type, float) and pd.isna(asset_type)) else str(asset_type).strip()
    combined = f"{raw} {asset_name or ''}".lower()
    if "municipal" in combined or " muni" in combined:
        return "Municipal Security"
    mapping = {
        "equity": "Stock",
        "stock": "Stock",
        "etf": "ETF",
        "mutual_fund": "Mutual Fund",
        "bond": "Bond",
        "option": "Option",
        "unknown": "Other",
    }
    if raw in mapping:
        return mapping[raw]
    if raw:
        return raw.replace("_", " ").title()
    return "Other"


def transaction_type_feed_label(raw: object) -> tuple[str, str]:
    s = "" if raw is None or (isinstance(raw, float) and pd.isna(raw)) else str(raw).strip()
    if s == "P":
        return "Purchase", "buy"
    if s == "S (partial)":
        return "Sale (Partial)", "sell-partial"
    if s == "S":
        return "Sale (Full)", "sell"
    if s == "E":
        return "Exchange", "exchange"
    return s or "Unknown", "unknown"


def _member_initials(name: str) -> str:
    parts = [p for p in re.split(r"\s+", name.strip()) if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _party_avatar_color(party: object) -> str:
    p = "" if party is None or (isinstance(party, float) and pd.isna(party)) else str(party).strip().lower()
    if p.startswith("r"):
        return THEME["accent"]
    if p.startswith("d"):
        return THEME["navy"]
    if p.startswith("i"):
        return THEME["teal"]
    return THEME["chart_unknown"]


def _chamber_party_line(chamber: object, party: object) -> str:
    ch = "" if chamber is None or (isinstance(chamber, float) and pd.isna(chamber)) else str(chamber).strip()
    pa = "" if party is None or (isinstance(party, float) and pd.isna(party)) else str(party).strip()
    if pa and len(pa) == 1:
        pa = pa.upper()
    if ch and pa:
        return f"{ch} / {pa}"
    return ch or pa or "—"


def _format_table_date(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"
    try:
        return pd.Timestamp(value).strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return "—"


def _stock_title(row: pd.Series) -> str:
    for col in ("issuer_name", "asset_name_normalized", "asset_name_raw", "ticker"):
        val = row.get(col)
        if val is not None and not (isinstance(val, float) and pd.isna(val)):
            s = str(val).strip()
            if s and s.lower() not in {"nan", "none", "-"}:
                return s.upper() if col == "ticker" else s
    return "—"


def _amount_label(row: pd.Series) -> str:
    raw = row.get("amount_range_raw")
    if raw is not None and not (isinstance(raw, float) and pd.isna(raw)):
        s = str(raw).strip()
        if s:
            return s
    return format_disclosed_range(row.get("amount_low"), row.get("amount_high"))


def _description_text(row: pd.Series, *, max_len: int = 72) -> str:
    for col in ("asset_name_raw", "asset_name_normalized"):
        val = row.get(col)
        if val is not None and not (isinstance(val, float) and pd.isna(val)):
            s = str(val).strip()
            if s:
                if len(s) > max_len:
                    return s[: max_len - 1].rstrip() + "…"
                return s
    return "—"


def _return_label(row: pd.Series) -> tuple[str, str]:
    raw = row.get("polygon_mkt_return_pct")
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return "—", "neutral"
    s = str(raw).strip()
    if not s:
        return "—", "neutral"
    try:
        pct = float(s)
    except ValueError:
        return "—", "neutral"
    sign = "+" if pct > 0 else ""
    tone = "up" if pct > 0 else "down" if pct < 0 else "neutral"
    return f"{sign}{pct:.1f}%", tone


def _stock_icon_svg() -> str:
    return (
        '<svg class="dt-stock-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="1.6" aria-hidden="true">'
        '<rect x="4" y="8" width="16" height="12" rx="1.5"/>'
        '<path d="M8 8V6a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>'
        '<path d="M9 13h2M13 13h2M9 16h6"/>'
        "</svg>"
    )


def _return_icon_svg() -> str:
    return (
        '<svg class="dt-return-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="1.8" aria-hidden="true">'
        '<path d="M4 16l4-4 4 3 8-8"/><path d="M16 7h4v4"/>'
        "</svg>"
    )


def _nav_link(text: str, page: str, param_name: str, param_value: str) -> str:
    """Wrap text in an anchor that navigates to a dashboard page with a query param."""
    return nav_link_params(text, page, {param_name: param_value})


def _transaction_row_html(row: pd.Series) -> str:
    stock_title = _escape(_stock_title(row))
    asset_sub = _escape(asset_type_feed_label(row.get("asset_type"), row.get("asset_name_raw")))
    txn_label, txn_class = transaction_type_feed_label(row.get("transaction_type"))
    txn_label = _escape(txn_label)
    amount = _escape(_amount_label(row))
    member_raw = str(row.get("member") or "Unknown")
    member = _escape(member_raw)
    initials = _escape(_member_initials(str(row.get("member") or "?")))
    avatar_color = _party_avatar_color(row.get("party"))
    chamber_party = _escape(_chamber_party_line(row.get("chamber"), row.get("party")))
    filed = _escape(_format_table_date(row.get("filing_date")))
    traded = _escape(_format_table_date(row.get("transaction_date")))
    ret_label, ret_tone = _return_label(row)
    ret_label = _escape(ret_label)

    ticker_raw = str(row.get("ticker") or "").strip()
    ticker_display = _escape(ticker_raw.upper()) if ticker_raw else "—"
    if ticker_raw:
        stock_link = nav_link_params(stock_title, "Tickers", {"ticker": ticker_raw})
        ticker_link = nav_link_params(ticker_display, "Tickers", {"ticker": ticker_raw})
    else:
        stock_link = stock_title
        ticker_link = ticker_display
    member_link = nav_link_params(member, "Members", {"member": member_raw})

    return (
        '<tr class="dt-row">'
        f'<td class="dt-cell dt-ticker">'
        f'<span class="dt-primary">{ticker_link}</span></td>'
        f'<td class="dt-cell dt-stock"><div class="dt-stock-wrap">{_stock_icon_svg()}'
        f'<div><div class="dt-primary">{stock_link}</div>'
        f'<div class="dt-secondary">{asset_sub}</div></div></div></td>'
        f'<td class="dt-cell dt-txn"><div class="dt-primary dt-txn-{txn_class}">{txn_label}</div>'
        f'<div class="dt-secondary">{amount}</div></td>'
        f'<td class="dt-cell dt-member"><div class="dt-member-wrap">'
        f'<div class="dt-avatar" style="background:{avatar_color};">{initials}</div>'
        f'<div><div class="dt-primary">{member_link}</div>'
        f'<div class="dt-secondary">{chamber_party}</div></div></div></td>'
        f'<td class="dt-cell dt-date">{filed}</td>'
        f'<td class="dt-cell dt-date">{traded}</td>'
        f'<td class="dt-cell dt-return dt-return-{ret_tone}">'
        f'<span class="dt-return-wrap">{_return_icon_svg()}<span>{ret_label}</span></span>'
        f"</td></tr>"
    )


def build_transaction_table_html(
    rows: pd.DataFrame,
    *,
    show_return_legend: bool = True,
) -> str:
    if rows.empty:
        return ""
    body_rows = "".join(_transaction_row_html(row) for _, row in rows.iterrows())
    legend = None
    if show_return_legend:
        legend = (
            f"{_return_icon_svg()}"
            f"<span>Estimated excess return of the underlying stock since the transaction</span>"
        )
    body = (
        "<thead><tr>"
        "<th>Ticker</th><th>Stock</th><th>Transaction</th><th>Politician</th>"
        "<th>Filed</th><th>Traded</th>"
        '<th class="dt-th-return"></th>'
        f"</tr></thead><tbody>{body_rows}</tbody>"
    )
    return table_shell(body=body, legend=legend, variant="dt-transactions", theme="light")


def build_summary_table_html(
    frame: pd.DataFrame,
    *,
    columns: list[str] | None = None,
    headers: dict[str, str] | None = None,
    link_columns: dict[str, dict[str, object]] | None = None,
    color_columns: dict[str, str] | None = None,
    theme: str = "light",
) -> str:
    config = TableConfig(
        variant="summary",
        theme=theme,  # type: ignore[arg-type]
        columns=columns,
        headers=headers or {},
        link_columns=link_columns or {},
        color_columns=color_columns or {},  # type: ignore[arg-type]
    )
    return build_table_html(frame, config)


@st.cache_data(show_spinner=False)
def _transaction_rows_with_polygon_cached(rows_json: str, as_of_iso: str) -> pd.DataFrame:
    del as_of_iso
    if not rows_json:
        return pd.DataFrame()
    base = pd.read_json(rows_json)
    if base.empty:
        return base
    return merge_polygon_pnl_cached_columns(base, as_of=date.today())


def prepare_transaction_table_rows(
    frame: pd.DataFrame,
    *,
    limit: int | None = 30,
    with_polygon: bool = True,
    sort: bool = True,
) -> pd.DataFrame:
    if frame.empty:
        return frame
    out = frame
    if sort:
        sort_cols = [c for c in ("transaction_date", "filing_date") if c in out.columns]
        if sort_cols:
            out = out.sort_values(sort_cols, ascending=[False] * len(sort_cols))
    if limit is not None:
        out = out.head(limit)
    if not with_polygon:
        return out.copy()
    rows_json = out.to_json(orient="records", date_format="iso")
    return _transaction_rows_with_polygon_cached(rows_json, date.today().isoformat())


def _render_sort_controls(widget_key: str) -> tuple[str, bool]:
    """Render sort-by pills + direction toggle. Returns (sort_column_df_name, ascending)."""
    sort_labels = list(_SORT_COLUMNS.keys())
    col_sort, col_dir = st.columns([5, 1], vertical_alignment="bottom")
    with col_sort:
        chosen = st.pills(
            "Sort by",
            sort_labels,
            default="Traded",
            key=f"{widget_key}_sort_col",
        )
    with col_dir:
        asc = st.toggle("↑", value=False, key=f"{widget_key}_sort_dir", help="Toggle ascending / descending")
    col_name = _SORT_COLUMNS.get(chosen, "transaction_date") if chosen else "transaction_date"
    return col_name, asc


def render_transaction_table(
    frame: pd.DataFrame,
    *,
    limit: int | None = 30,
    with_polygon: bool = True,
    show_return_legend: bool = True,
    sort: bool = True,
    empty_message: str = "No transactions in the current filter.",
    widget_key: str = "txn_table",
) -> None:
    if frame.empty:
        st.info(empty_message)
        return

    sort_col, sort_asc = _render_sort_controls(widget_key)

    rows = prepare_transaction_table_rows(
        frame,
        limit=limit,
        with_polygon=with_polygon,
        sort=False,
    )
    if rows.empty:
        st.info(empty_message)
        return

    if sort_col in rows.columns:
        rows = rows.sort_values(sort_col, ascending=sort_asc, na_position="last")

    _render_table_html(build_transaction_table_html(rows, show_return_legend=show_return_legend))


def render_summary_table(
    frame: pd.DataFrame,
    *,
    columns: list[str] | None = None,
    headers: dict[str, str] | None = None,
    link_columns: dict[str, dict[str, object]] | None = None,
    color_columns: dict[str, str] | None = None,
    theme: str = "light",
    empty_message: str = "No rows to display.",
) -> None:
    render_table(
        frame,
        TableConfig(
            variant="summary",
            theme=theme,  # type: ignore[arg-type]
            columns=columns,
            headers=headers or {},
            link_columns=link_columns or {},
            color_columns=color_columns or {},  # type: ignore[arg-type]
            empty_message=empty_message,
        ),
    )


# Backward-compatible aliases
build_activity_feed_html = build_transaction_table_html
render_activity_feed = render_transaction_table
prepare_activity_feed_rows = prepare_transaction_table_rows
