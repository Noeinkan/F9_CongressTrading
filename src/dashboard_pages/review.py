from __future__ import annotations

import pandas as pd
import streamlit as st

from src.dashboard_shared import (
    _build_mix_chart,
    _copy,
    _render_section_intro,
    _style_dataframe_buy_sell,
    get_dashboard_context,
)

ctx = get_dashboard_context()
if not ctx["ready"]:
    st.warning("No data loaded.")
    st.stop()

filtered_review: pd.DataFrame = ctx["review"]  # type: ignore[assignment]

_render_section_intro(
    _copy("review_kicker"),
    _copy("review_title"),
    _copy("review_copy"),
)

st.subheader(_copy("sub_records_needing_review"))
if filtered_review.empty:
    st.success("No records currently require review for the selected filter.")
else:
    review_reason_counts = (
        filtered_review.groupby("reason", as_index=False)
        .size()
        .rename(columns={"size": "records"})
        .sort_values("records", ascending=False)
    )
    review_status_counts = (
        filtered_review.groupby("status", as_index=False)
        .size()
        .rename(columns={"size": "records"})
        .sort_values("records", ascending=False)
    )
    review_cols = st.columns(2)
    with review_cols[0]:
        st.caption(_copy("chart_caption_mix_review_reason"))
        st.altair_chart(
            _build_mix_chart(
                review_reason_counts.rename(columns={"records": "transactions"}),
                "reason",
                color="#20344a",
                x_axis_title="Review reason",
            ),
            width="stretch",
        )
    with review_cols[1]:
        st.caption(_copy("chart_caption_mix_review_status"))
        st.altair_chart(
            _build_mix_chart(
                review_status_counts.rename(columns={"records": "transactions"}),
                "status",
                color="#a64b2a",
                x_axis_title="Review status",
            ),
            width="stretch",
        )
    _review_df = filtered_review.sort_values(["transaction_date", "filing_date"], ascending=[False, False])
    st.dataframe(
        _style_dataframe_buy_sell(_review_df),
        hide_index=True,
        width="stretch",
        height=520,
        column_config={
            "transaction_date": st.column_config.DateColumn("Transaction Date", format="YYYY-MM-DD"),
            "filing_date": st.column_config.DateColumn("Filing Date", format="YYYY-MM-DD"),
        },
    )
