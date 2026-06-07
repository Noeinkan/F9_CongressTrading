from __future__ import annotations



import pandas as pd

import streamlit as st



from src.dashboard_shared import (

    THEME,

    _build_mix_chart,

    _copy,

    _render_section_intro,

    chart_card,


    render_summary_table,

    render_transaction_table,

)


def render(ctx: dict[str, object]) -> None:
    """Dashboard page — called from dashboard.py dispatch."""
    if not ctx["ready"]:
        st.warning("No data loaded.")
        return



    filtered_review: pd.DataFrame = ctx["review"]  # type: ignore[assignment]



    _render_section_intro(

        _copy("review_kicker"),

        _copy("review_title"),

        _copy("review_copy"),

    )



    with chart_card(_copy("sub_records_needing_review")):

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

                st.markdown("**By reason**")

                st.caption(_copy("chart_caption_mix_review_reason"))

                st.altair_chart(

                    _build_mix_chart(

                        review_reason_counts.rename(columns={"records": "transactions"}),

                        "reason",

                        color=THEME["chart_series_primary"],

                        x_axis_title="Review reason",

                    ),

                    width="stretch",

                )

            with review_cols[1]:

                st.markdown("**By status**")

                st.caption(_copy("chart_caption_mix_review_status"))

                st.altair_chart(

                    _build_mix_chart(

                        review_status_counts.rename(columns={"records": "transactions"}),

                        "status",

                        color=THEME["accent"],

                        x_axis_title="Review status",

                    ),

                    width="stretch",

                )

            render_summary_table(

                filtered_review.sort_values(["transaction_date", "filing_date"], ascending=[False, False])[

                    ["reason", "status", "member", "ticker", "transaction_type", "amount_range_raw", "confidence_score"]

                ],

                headers={

                    "reason": "Reason",

                    "status": "Status",

                    "member": "Member",

                    "ticker": "Ticker",

                    "transaction_type": "Type",

                    "amount_range_raw": "Amount",

                    "confidence_score": "Confidence",

                },

            )

            st.markdown("**Full transaction detail**")

            render_transaction_table(

                filtered_review,

                limit=40,

                with_polygon=False,

                show_return_legend=False,

            )

