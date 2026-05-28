from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from src.dashboard_shared import (
    _copy,
    _download_bytes,
    _polygon_daily_bar_cache_size,
    _render_section_intro,
    _style_dataframe_buy_sell,
    get_connection,
    get_dashboard_context,
    init_db,
    merge_polygon_pnl_cached_columns,
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

st.subheader(_copy("sub_filtered_dataset"))
show_polygon_est = st.checkbox(
    "Show Polygon return estimates (SQLite cache only; no API calls from this page)",
    value=False,
    key="raw_polygon_estimates",
)
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
_raw_df = _raw_base
if show_polygon_est:
    if polygon_cache_rows == 0:
        st.info(
            "Polygon daily bar cache is empty. Run "
            "`python -m src.main warm-polygon-price-cache` (requires `POLYGON_API_KEY`), then refresh."
        )
    else:
        _raw_df = merge_polygon_pnl_cached_columns(_raw_base, as_of=date.today())

st.download_button(
    label="Download filtered transactions as CSV",
    data=_download_bytes(_raw_df),
    file_name="congress_transactions_filtered.csv",
    mime="text/csv",
)
st.dataframe(
    _style_dataframe_buy_sell(_raw_df),
    hide_index=True,
    width="stretch",
    height=620,
    column_config={
        "transaction_date": st.column_config.DateColumn("Transaction Date", format="YYYY-MM-DD"),
        "filing_date": st.column_config.DateColumn("Filing Date", format="YYYY-MM-DD"),
        "amount_low": st.column_config.NumberColumn("Amount Low", format="$%d"),
        "amount_high": st.column_config.NumberColumn("Amount High", format="$%d"),
        "estimated_value": st.column_config.NumberColumn("Median of range", format="$%d"),
    },
)
