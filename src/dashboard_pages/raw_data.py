from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from src.dashboard_shared import (
    _copy,
    _download_bytes,
    _polygon_daily_bar_cache_size,
    _render_section_intro,
    get_connection,
    get_dashboard_context,
    init_db,
    chart_card,
    render_transaction_table,
)

ctx = get_dashboard_context()
if not ctx["ready"]:
    st.warning("No data loaded.")
    st.stop()

filtered: pd.DataFrame = ctx["filtered"]  # type: ignore[assignment]

_render_section_intro(
    _copy("raw_kicker"),
    _copy("raw_title"),
    _copy("raw_copy"),
)

show_polygon_est = st.checkbox(
    "Show Polygon return estimates (SQLite cache only; no API calls from this page)",
    value=False,
    key="raw_polygon_estimates",
)
row_limit = st.slider("Rows to display", min_value=10, max_value=200, value=50, step=10, key="raw_row_limit")
st.caption(
    "Populates `polygon_daily_bar_cache` via CLI: `python -m src.main warm-polygon-price-cache` "
    "or `python -m src.main export-csv --polygon-pnl --as-of YYYY-MM-DD`."
)
conn_poly = get_connection()
try:
    init_db(conn_poly)
    polygon_cache_rows = _polygon_daily_bar_cache_size(conn_poly)
finally:
    conn_poly.close()

_raw_base = filtered.sort_values(["transaction_date", "filing_date"], ascending=[False, False])
if show_polygon_est and polygon_cache_rows == 0:
    st.info(
        "Polygon daily bar cache is empty. Run "
        "`python -m src.main warm-polygon-price-cache` (requires `POLYGON_API_KEY`), then refresh."
    )

with chart_card(_copy("sub_filtered_dataset")):
    st.download_button(
        label="Download filtered transactions as CSV",
        data=_download_bytes(_raw_base),
        file_name="congress_transactions_filtered.csv",
        mime="text/csv",
    )
    render_transaction_table(
        _raw_base,
        limit=row_limit,
        with_polygon=show_polygon_est and polygon_cache_rows > 0,
    )
