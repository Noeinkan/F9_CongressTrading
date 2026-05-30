from __future__ import annotations

import html
import re
from datetime import date
from urllib.parse import quote

import pandas as pd
import streamlit as st

from .constants import THEME
from .data import merge_polygon_pnl_cached_columns
from .formatting import format_disclosed_range
from .styles import _streamlit_theme_is_dark

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


def _escape(text: object) -> str:
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return ""
    return html.escape(str(text))


def _table_theme_class() -> str:
    # Match the warm dashboard shell; avoid navy-in-cream contrast unless Streamlit is fully dark.
    if _streamlit_theme_is_dark():
        return "dt-dark"
    return "dt-light"


def _render_table_html(html_out: str) -> None:
    """Render table HTML without markdown (indented tags become code blocks in st.markdown)."""
    st.html(html_out)


def _sort_css() -> str:
    """Inline CSS for sort indicators — must live inside the st.html context."""
    return """<style>
.dt-table th[data-sort-dir]{position:relative;padding-right:1.25rem;cursor:pointer;user-select:none;}
.dt-table th[data-sort-dir]::after{content:'⇅';position:absolute;right:0.3rem;top:50%;
  transform:translateY(-50%);font-size:0.62rem;opacity:0.35;}
.dt-table th.dt-sort-asc::after{content:'▲';opacity:0.8;}
.dt-table th.dt-sort-desc::after{content:'▼';opacity:0.8;}
</style>"""


def _sort_js() -> str:
    """Client-side table sorting via header clicks. Injected once per table."""
    return """<script>
(function(){
  function sortVal(td){
    if(!td)return '';
    var v=td.getAttribute('data-sort-value');
    return(v!==null&&v!=='')?v:td.textContent.trim();
  }
  function cmp(a,b){
    if(a===b)return 0;
    // ISO-ish date strings — compare lexicographically (works for YYYY-MM-DD…)
    if(a.length>7&&b.length>7&&a[4]==='-'&&b[4]==='-')return a<b?-1:1;
    // Pure numbers
    var an=Number(a),bn=Number(b);
    if(a!==''&&b!==''&&!isNaN(an)&&!isNaN(bn))return an-bn;
    return a.localeCompare(b);
  }
  var tables=document.currentScript.parentElement.querySelectorAll('.dt-table');
  tables.forEach(function(tbl){
    var heads=tbl.querySelectorAll('thead th');
    heads.forEach(function(th,ci){
      if(th.classList.contains('dt-th-return'))return;
      th.style.cursor='pointer';th.style.userSelect='none';
      th.setAttribute('data-sort-dir','');
      th.addEventListener('click',function(){
        var dir=th.getAttribute('data-sort-dir')==='asc'?'desc':'asc';
        heads.forEach(function(h){h.setAttribute('data-sort-dir','');
          h.classList.remove('dt-sort-asc','dt-sort-desc');});
        th.setAttribute('data-sort-dir',dir);
        th.classList.add(dir==='asc'?'dt-sort-asc':'dt-sort-desc');
        var tbody=tbl.querySelector('tbody');
        var rows=Array.from(tbody.querySelectorAll('tr'));
        rows.sort(function(ra,rb){
          var va=sortVal(ra.children[ci]),vb=sortVal(rb.children[ci]);
          var r=cmp(va,vb);
          return dir==='asc'?r:-r;
        });
        rows.forEach(function(r){tbody.appendChild(r);});
      });
    });
  });
})();
</script>"""


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


def _format_summary_cell(column: str, value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"
    if column in _DATE_COLUMNS:
        return _format_table_date(value)
    if isinstance(value, float) and column not in ("spike_ratio", "recent_per_month", "prior_per_month", "call_put_ratio"):
        if value == int(value):
            return f"{int(value):,}"
        return f"{value:,.2f}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


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


def _table_shell(*, body: str, legend: str | None, variant: str, sortable: bool = False) -> str:
    theme = _table_theme_class()
    legend_html = f'<div class="dt-legend">{legend}</div>' if legend else ""
    sort_block = (_sort_css() + _sort_js()) if sortable else ""
    return (
        f'<div class="dashboard-table {theme} {variant}">'
        f"{legend_html}"
        f'<div class="dt-scroll"><table class="dt-table">{body}</table></div>'
        f"{sort_block}"
        f"</div>"
    )


def _nav_link(text: str, page: str, param_name: str, param_value: str) -> str:
    """Wrap text in an anchor that navigates to a dashboard page with a query param."""
    url_value = quote(param_value, safe="")
    return (
        f'<a class="dt-nav-link" href="/{page}?{param_name}={url_value}" '
        f'target="_parent">{text}</a>'
    )


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
        stock_link = _nav_link(stock_title, "Tickers", "ticker", ticker_raw)
        ticker_link = _nav_link(ticker_display, "Tickers", "ticker", ticker_raw)
    else:
        stock_link = stock_title
        ticker_link = ticker_display
    member_link = _nav_link(member, "Members", "member", member_raw)

    filing_sort = ""
    trade_sort = ""
    try:
        filing_sort = pd.Timestamp(row.get("filing_date")).isoformat()
    except Exception:
        pass
    try:
        trade_sort = pd.Timestamp(row.get("transaction_date")).isoformat()
    except Exception:
        pass

    return (
        '<tr class="dt-row">'
        f'<td class="dt-cell dt-ticker" data-sort-value="{ticker_display}">'
        f'<span class="dt-primary">{ticker_link}</span></td>'
        f'<td class="dt-cell dt-stock" data-sort-value="{stock_title}"><div class="dt-stock-wrap">{_stock_icon_svg()}'
        f'<div><div class="dt-primary">{stock_link}</div>'
        f'<div class="dt-secondary">{asset_sub}</div></div></div></td>'
        f'<td class="dt-cell dt-txn" data-sort-value="{txn_label}"><div class="dt-primary dt-txn-{txn_class}">{txn_label}</div>'
        f'<div class="dt-secondary">{amount}</div></td>'
        f'<td class="dt-cell dt-member" data-sort-value="{member}"><div class="dt-member-wrap">'
        f'<div class="dt-avatar" style="background:{avatar_color};">{initials}</div>'
        f'<div><div class="dt-primary">{member_link}</div>'
        f'<div class="dt-secondary">{chamber_party}</div></div></div></td>'
        f'<td class="dt-cell dt-date" data-sort-value="{filing_sort}">{filed}</td>'
        f'<td class="dt-cell dt-date" data-sort-value="{trade_sort}">{traded}</td>'
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
    return _table_shell(body=body, legend=legend, variant="dt-transactions", sortable=True)


def build_summary_table_html(
    frame: pd.DataFrame,
    *,
    columns: list[str] | None = None,
    headers: dict[str, str] | None = None,
) -> str:
    if frame.empty:
        return ""
    cols = columns or list(frame.columns)
    cols = [c for c in cols if c in frame.columns]
    if not cols:
        return ""
    labels = headers or {}
    head = "".join(f"<th>{_escape(labels.get(c, c.replace('_', ' ').title()))}</th>" for c in cols)
    body_rows: list[str] = []
    for _, row in frame.iterrows():
        cells = "".join(
            f'<td class="dt-cell"><span class="dt-plain">{_escape(_format_summary_cell(c, row.get(c)))}</span></td>'
            for c in cols
        )
        body_rows.append(f'<tr class="dt-row">{cells}</tr>')
    body = f"<thead><tr>{head}</tr></thead><tbody>{''.join(body_rows)}</tbody>"
    return _table_shell(body=body, legend=None, variant="dt-summary")


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


def render_transaction_table(
    frame: pd.DataFrame,
    *,
    limit: int | None = 30,
    with_polygon: bool = True,
    show_return_legend: bool = True,
    sort: bool = True,
    empty_message: str = "No transactions in the current filter.",
) -> None:
    rows = prepare_transaction_table_rows(
        frame,
        limit=limit,
        with_polygon=with_polygon,
        sort=sort,
    )
    if rows.empty:
        st.info(empty_message)
        return
    _render_table_html(build_transaction_table_html(rows, show_return_legend=show_return_legend))


def render_summary_table(
    frame: pd.DataFrame,
    *,
    columns: list[str] | None = None,
    headers: dict[str, str] | None = None,
    empty_message: str = "No rows to display.",
) -> None:
    if frame.empty:
        st.info(empty_message)
        return
    html_out = build_summary_table_html(frame, columns=columns, headers=headers)
    if not html_out:
        st.info(empty_message)
        return
    _render_table_html(html_out)


# Backward-compatible aliases
build_activity_feed_html = build_transaction_table_html
render_activity_feed = render_transaction_table
prepare_activity_feed_rows = prepare_transaction_table_rows
