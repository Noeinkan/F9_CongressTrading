from __future__ import annotations

import altair as alt
import numpy as np
import pandas as pd

from .constants import THEME
from .components import _copy
from .data import (
    _signed_trade_notional,
    load_polygon_bars,
    transaction_type_display_label,
)
from .styles import _altair_readability

def _build_time_series_chart(frame: pd.DataFrame) -> alt.Chart:
    chart_data = frame.copy()
    chart_data["month_label"] = chart_data["month"].dt.strftime("%b %Y")

    base = (
        alt.Chart(chart_data)
        .mark_area(line={"color": THEME["accent"], "strokeWidth": 3}, color="#d7a869", opacity=0.35)
        .encode(
            x=alt.X(
                "month:T",
                axis=alt.Axis(
                    title="Calendar month",
                    labelColor=THEME["chart_axis_label"],
                    titleColor=THEME["chart_axis_title"],
                    grid=True,
                    gridColor=THEME["chart_grid_major"],
                    format="%b %Y",
                ),
            ),
            y=alt.Y(
                "transactions:Q",
                axis=alt.Axis(
                    title="Disclosure rows in month",
                    labelColor=THEME["chart_axis_label"],
                    titleColor=THEME["chart_axis_title"],
                    tickCount=5,
                    gridColor=THEME["chart_grid_major"],
                ),
            ),
            tooltip=[
                alt.Tooltip("month_label:N", title="Month"),
                alt.Tooltip("transactions:Q", title="Transactions", format=",.0f"),
                alt.Tooltip("estimated_value:Q", title="Estimated Midpoint", format="$,.0f"),
            ],
        )
        .properties(height=300)
        .configure(background="transparent")
    )
    return _altair_readability(base)


def _build_rank_chart(
    frame: pd.DataFrame,
    label_field: str,
    title: str,
    *,
    color: str,
    y_axis_title: str | None = None,
) -> alt.Chart:
    chart_data = frame.copy()
    chart_data = chart_data.sort_values("transactions", ascending=False)
    y_title = y_axis_title or label_field.replace("_", " ").title()

    base = (
        alt.Chart(chart_data)
        .mark_bar(cornerRadiusTopRight=6, cornerRadiusBottomRight=6, color=color)
        .encode(
            x=alt.X(
                "transactions:Q",
                axis=alt.Axis(
                    title=title,
                    labelColor=THEME["chart_axis_label"],
                    titleColor=THEME["chart_axis_title"],
                    tickCount=5,
                    gridColor=THEME["chart_grid_major"],
                ),
            ),
            y=alt.Y(
                f"{label_field}:N",
                sort="-x",
                axis=alt.Axis(
                    title=y_title,
                    labelColor=THEME["chart_axis_label"],
                    titleColor=THEME["chart_axis_title"],
                    labelLimit=220,
                ),
            ),
            tooltip=[
                alt.Tooltip(f"{label_field}:N", title=title.rstrip("s")),
                alt.Tooltip("transactions:Q", title="Transactions", format=",.0f"),
                alt.Tooltip("estimated_value:Q", title="Estimated Midpoint", format="$,.0f"),
            ],
        )
        .properties(height=320)
        .configure(background="transparent")
    )
    return _altair_readability(base)


def _build_mix_chart(
    frame: pd.DataFrame,
    label_field: str,
    *,
    color: str,
    x_axis_title: str | None = None,
) -> alt.Chart:
    chart_data = frame.copy()
    x_title = x_axis_title or label_field.replace("_", " ").title()
    base = (
        alt.Chart(chart_data)
        .mark_bar(cornerRadiusTopLeft=8, cornerRadiusTopRight=8, color=color)
        .encode(
            x=alt.X(
                f"{label_field}:N",
                axis=alt.Axis(
                    title=x_title,
                    labelColor=THEME["chart_axis_label"],
                    titleColor=THEME["chart_axis_title"],
                    labelAngle=-25,
                    labelLimit=180,
                ),
            ),
            y=alt.Y(
                "transactions:Q",
                axis=alt.Axis(
                    title="Row count",
                    labelColor=THEME["chart_axis_label"],
                    titleColor=THEME["chart_axis_title"],
                    tickCount=4,
                    grid=True,
                    gridColor=THEME["chart_grid_major"],
                ),
            ),
            tooltip=[
                alt.Tooltip(f"{label_field}:N", title=label_field.replace("_", " ").title()),
                alt.Tooltip("transactions:Q", title="Transactions", format=",.0f"),
            ],
        )
        .properties(height=250)
        .configure(background="transparent")
    )
    return _altair_readability(base)


# Semantic colors for the member × time scatter (explicit domain avoids Altair assigning
# theme colors alphabetically, which obscures buy vs sell).
_TICKER_TIMELINE_TYPE_COLORS: dict[str, str] = {
    "Buy": "#15803d",
    "Sell": "#be123c",
    "Sell (partial)": "#c2410c",
    "Exchange": "#1d4ed8",
    "Unknown": "#64748b",
}


def _ticker_timeline_vertical_rule_dates(series: pd.Series) -> pd.DatetimeIndex:
    """Month-start rules for readability; weekly when the filtered window is short."""
    t0 = pd.Timestamp(series.min()).normalize()
    t1 = pd.Timestamp(series.max())
    span_days = max(1, int((t1 - t0).days) + 1)
    if span_days <= 100:
        return pd.date_range(t0 - pd.Timedelta(days=t0.weekday()), t1 + pd.Timedelta(days=1), freq="W-MON")
    if span_days <= 800:
        start = t0.to_period("M").to_timestamp()
        return pd.date_range(start, t1 + pd.Timedelta(days=1), freq="MS")
    start = t0.to_period("Q").to_timestamp()
    return pd.date_range(start, t1 + pd.Timedelta(days=1), freq="QS")


def _ticker_timeline_x_axis_format(span_days: int) -> tuple[str, int]:
    if span_days <= 45:
        return ("%d %b %y", min(18, max(6, span_days // 2)))
    if span_days <= 550:
        return ("%b '%y", 14)
    return ("%Y", max(4, min(12, span_days // 200)))


def _ticker_timeline_color_key_html(labels_in_use: list[str]) -> str:
    parts = []
    for lab in labels_in_use:
        c = _TICKER_TIMELINE_TYPE_COLORS.get(lab, "#64748b")
        parts.append(
            f'<span style="display:inline-flex;align-items:center;gap:0.35rem;margin-right:1rem;">'
            f'<span style="width:0.65rem;height:0.65rem;border-radius:999px;background:{c};'
            f'border:1px solid rgba(0,0,0,0.12);"></span>{lab}</span>'
        )
    inner = "".join(parts)
    return (
        f'<p style="margin:0.35rem 0 0.75rem 0;font-size:0.95rem;font-weight:500;color:{THEME["ui_caption"]};">'
        f"<strong>{_copy('ticker_color_key_title')}</strong> · {inner}</p>"
    )


def _build_ticker_member_timeline(frame: pd.DataFrame, ticker: str) -> alt.Chart | None:
    if not ticker or not str(ticker).strip():
        return None
    t = str(ticker).strip().upper()
    sub = frame[frame["ticker"].astype(str).str.upper() == t].copy()
    sub = sub.dropna(subset=["transaction_date"])
    if sub.empty:
        return None
    sub["txn_type_label"] = sub["transaction_type"].map(transaction_type_display_label)
    preferred = ["Buy", "Sell", "Sell (partial)", "Exchange", "Unknown"]
    present = sub["txn_type_label"].drop_duplicates().tolist()
    color_domain = [x for x in preferred if x in present] + sorted(x for x in present if x not in preferred)
    color_range = [_TICKER_TIMELINE_TYPE_COLORS.get(x, "#64748b") for x in color_domain]
    member_order = (
        sub.groupby("member", observed=True)["transaction_date"]
        .max()
        .sort_values(ascending=False)
        .index.tolist()
    )
    height = min(520, max(220, 32 * max(6, len(member_order))))
    span_days = max(1, int((sub["transaction_date"].max() - sub["transaction_date"].min()).days) + 1)
    date_fmt, tick_n = _ticker_timeline_x_axis_format(span_days)
    grid_axis = THEME["chart_grid_major"]
    x_axis = alt.Axis(
        title="Transaction date",
        format=date_fmt,
        tickCount=tick_n,
        labelAngle=-28,
        labelOverlap=False,
        labelColor=THEME["chart_axis_label"],
        titleColor=THEME["chart_axis_title"],
        grid=True,
        gridColor=grid_axis,
        gridDash=[2, 3],
        domainColor=THEME["chart_axis_title"],
        tickColor=THEME["chart_axis_label"],
        domainWidth=1,
    )
    y_axis = alt.Axis(
        title="Member",
        labelColor=THEME["chart_axis_label"],
        titleColor=THEME["chart_axis_title"],
        labelFontSize=12,
        labelLimit=240,
        grid=True,
        gridColor="rgba(18, 24, 34, 0.12)",
        domainColor=THEME["chart_axis_title"],
        tickColor=THEME["chart_axis_label"],
    )
    rules_df = pd.DataFrame({"transaction_date": _ticker_timeline_vertical_rule_dates(sub["transaction_date"])})
    vlines = (
        alt.Chart(rules_df)
        .mark_rule(
            color="rgba(32, 52, 74, 0.38)",
            strokeWidth=1,
            strokeDash=[5, 4],
        )
        .encode(x=alt.X("transaction_date:T", axis=None))
    )
    points = (
        alt.Chart(sub)
        .mark_circle(size=96, opacity=0.92, stroke="#ffffff", strokeWidth=1)
        .encode(
            x=alt.X("transaction_date:T", axis=x_axis),
            y=alt.Y("member:N", sort=member_order, axis=y_axis),
            color=alt.Color(
                "txn_type_label:N",
                title="Transaction type",
                scale=alt.Scale(domain=color_domain, range=color_range),
                legend=alt.Legend(
                    orient="bottom",
                    direction="horizontal",
                    titleFontWeight="bold",
                    labelColor=THEME["chart_legend_label"],
                    titleColor=THEME["chart_legend_title"],
                    labelLimit=220,
                    labelFontSize=13,
                    titleFontSize=14,
                    padding=12,
                    symbolType="circle",
                    symbolSize=130,
                ),
            ),
            tooltip=[
                alt.Tooltip("member:N", title="Member"),
                alt.Tooltip("transaction_date:T", title="Date", format="%Y-%m-%d"),
                alt.Tooltip("txn_type_label:N", title="Type"),
                alt.Tooltip("transaction_type:N", title="Raw code"),
                alt.Tooltip("amount_range_raw:N", title="Amount range"),
                alt.Tooltip("issuer_name:N", title="Issuer"),
                alt.Tooltip("chamber:N", title="Chamber"),
            ],
        )
    )
    base = (
        (vlines + points)
        .properties(height=height)
        .configure(background="transparent")
    )
    return _altair_readability(base)


def _build_ticker_3d_figure(frame: pd.DataFrame, ticker: str):
    """Plotly 3D scatter: date × member × log amount. Returns None if plotly missing or no rows."""
    try:
        import plotly.graph_objects as go
    except ImportError:
        return None
    if not ticker or not str(ticker).strip():
        return None
    t = str(ticker).strip().upper()
    sub = frame[frame["ticker"].astype(str).str.upper() == t].copy()
    sub = sub.dropna(subset=["transaction_date"])
    if sub.empty:
        return None
    sub = sub.copy()
    sub["txn_type_label"] = sub["transaction_type"].map(transaction_type_display_label)
    ev = pd.to_numeric(sub["estimated_value"], errors="coerce").fillna(0.0)
    sub["_z"] = np.log10(ev.clip(lower=0.0) + 1.0)
    member_order = (
        sub.groupby("member", observed=True)["transaction_date"]
        .max()
        .sort_values(ascending=False)
        .index.tolist()
    )
    sub["member"] = pd.Categorical(sub["member"], categories=member_order, ordered=True)
    sub = sub.sort_values(["transaction_date", "member"])
    color_map = {k: v for k, v in _TICKER_TIMELINE_TYPE_COLORS.items() if k in sub["txn_type_label"].unique()}
    traces = []
    for lab, g in sub.groupby("txn_type_label", observed=True):
        c = color_map.get(lab, _TICKER_TIMELINE_TYPE_COLORS.get(lab, "#64748b"))
        traces.append(
            go.Scatter3d(
                x=g["transaction_date"],
                y=g["member"].astype(str),
                z=g["_z"],
                mode="markers",
                name=lab,
                marker=dict(size=8, color=c, line=dict(width=0.5, color="rgba(255,255,255,0.9)")),
                hovertemplate=(
                    "<b>%{y}</b><br>"
                    "%{x|%Y-%m-%d}<br>"
                    "z = log₁₀(mid+1): %{z:.2f}<br>"
                    "<extra></extra>"
                ),
            )
        )
    ink = THEME["plotly_axis_ink"]
    tick = THEME["plotly_tick_ink"]
    leg = THEME["plotly_legend_ink"]
    bg = THEME["plotly_scene_bg"]
    grid_muted = "rgba(24, 32, 44, 0.38)"
    axis_title = dict(color=ink, size=14)
    tick_font = dict(color=tick, size=12)
    fig = go.Figure(data=traces)
    fig.update_layout(
        height=min(920, max(560, 30 * max(8, len(member_order)))),
        margin=dict(l=8, r=8, t=20, b=100),
        paper_bgcolor=THEME["plotly_paper"],
        font=dict(color=leg, size=13),
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.14,
            xanchor="center",
            x=0.5,
            bgcolor="rgba(255, 252, 246, 0.96)",
            bordercolor="rgba(18, 24, 34, 0.18)",
            borderwidth=1,
            title=dict(text="Transaction type", font=dict(color=leg, size=14)),
            font=dict(color=leg, size=13),
        ),
        scene=dict(
            xaxis=dict(
                title=dict(text="Date", font=axis_title),
                backgroundcolor=bg,
                gridcolor=grid_muted,
                showbackground=True,
                showspikes=True,
                spikecolor="rgba(166,75,42,0.55)",
                tickfont=tick_font,
            ),
            yaxis=dict(
                title=dict(text="Member", font=axis_title),
                backgroundcolor=bg,
                gridcolor=grid_muted,
                showbackground=True,
                tickfont=dict(color=tick, size=11),
                categoryorder="array",
                categoryarray=[str(m) for m in member_order],
            ),
            zaxis=dict(
                title=dict(text="log₁₀(est. midpoint + 1)", font=axis_title),
                backgroundcolor=bg,
                gridcolor=grid_muted,
                showbackground=True,
                tickfont=tick_font,
            ),
            aspectmode="manual",
            aspectratio=dict(x=2.0, y=1.35, z=0.85),
        ),
    )
    return fig


def _build_member_cumulative_notional_chart(
    frame: pd.DataFrame, ticker: str, *, top_n: int = 16
) -> tuple[alt.Chart | None, list[str]]:
    if not ticker or not str(ticker).strip():
        return None, []
    t = str(ticker).strip().upper()
    sub = frame[frame["ticker"].astype(str).str.upper().eq(t)].copy()
    sub = sub.dropna(subset=["transaction_date"])
    if sub.empty:
        return None, []

    sub["_signed"] = sub.apply(_signed_trade_notional, axis=1)
    member_counts = sub["member"].value_counts()
    keep_members = member_counts.head(top_n).index.tolist()
    sub = sub[sub["member"].isin(keep_members)]
    if sub.empty:
        return None, []

    sub = sub.sort_values(["member", "transaction_date", "filing_date"], ascending=[True, True, True])
    sub["cumulative_usd"] = sub.groupby("member", observed=True)["_signed"].cumsum()
    sub["trade_date_label"] = sub["transaction_date"].dt.strftime("%Y-%m-%d")
    sub["txn_type_label"] = sub["transaction_type"].map(transaction_type_display_label)

    member_order = sorted(sub["member"].dropna().astype(str).unique().tolist())
    n_members = len(member_order)
    height = min(480, max(240, 36 * max(4, min(n_members, 8))))

    chart = (
        alt.Chart(sub)
        .mark_line(point=True, strokeWidth=2.2, interpolate="monotone")
        .encode(
            x=alt.X(
                "transaction_date:T",
                title="Transaction date",
                axis=alt.Axis(
                    labelColor=THEME["chart_axis_label"],
                    titleColor=THEME["chart_axis_title"],
                    gridColor=THEME["chart_grid_major"],
                ),
            ),
            y=alt.Y(
                "cumulative_usd:Q",
                title="Cumulative signed median ($)",
                axis=alt.Axis(
                    labelColor=THEME["chart_axis_label"],
                    titleColor=THEME["chart_axis_title"],
                    tickCount=5,
                    gridColor=THEME["chart_grid_major"],
                    format="~s",
                ),
            ),
            color=alt.Color(
                "member:N",
                title="Member",
                scale=alt.Scale(domain=member_order),
                legend=alt.Legend(
                    orient="bottom",
                    direction="horizontal",
                    columns=min(3, max(1, n_members)),
                    title="Member (line color)",
                    labelFontSize=13,
                    titleFontSize=14,
                    titleFontWeight="bold",
                    labelFontWeight=500,
                    labelColor=THEME["chart_legend_label"],
                    titleColor=THEME["chart_legend_title"],
                    symbolSize=80,
                    symbolStrokeWidth=2,
                    columnPadding=14,
                    rowPadding=8,
                    padding=12,
                ),
            ),
            tooltip=[
                alt.Tooltip("member:N", title="Member"),
                alt.Tooltip("trade_date_label:N", title="Date"),
                alt.Tooltip("txn_type_label:N", title="Type"),
                alt.Tooltip("_signed:Q", title="Signed Δ ($)", format=",.0f"),
                alt.Tooltip("cumulative_usd:Q", title="Cumulative ($)", format=",.0f"),
                alt.Tooltip("amount_range_raw:N", title="Amount range"),
            ],
        )
        .properties(height=height)
        .configure(
            background="transparent",
            padding={"bottom": 110},
            view={
                "fill": THEME["chart_view_fill"],
                "stroke": THEME["chart_view_stroke"],
                "strokeWidth": 1,
            },
            legend={
                "labelColor": THEME["chart_legend_label"],
                "titleColor": THEME["chart_legend_title"],
                "labelFontSize": 13,
                "titleFontSize": 14,
                "strokeColor": "rgba(12, 16, 24, 0.12)",
                "fillColor": "rgba(255, 252, 246, 0.98)",
            },
        )
    )
    return chart, member_order

def _build_member_activity_timeline(frame: pd.DataFrame, member: str) -> alt.Chart | None:
    sub = frame.loc[frame["member"].astype(str) == str(member)].copy()
    sub = sub.dropna(subset=["transaction_date"])
    sub = sub[sub["ticker"].astype(str).str.strip() != ""]
    if sub.empty:
        return None
    sub["txn_type_label"] = sub["transaction_type"].map(transaction_type_display_label)
    preferred = ["Buy", "Sell", "Sell (partial)", "Exchange", "Unknown"]
    present = sub["txn_type_label"].drop_duplicates().tolist()
    color_domain = [x for x in preferred if x in present] + sorted(x for x in present if x not in preferred)
    color_range = [_TICKER_TIMELINE_TYPE_COLORS.get(x, "#64748b") for x in color_domain]
    ticker_order = (
        sub.groupby("ticker", observed=True)["transaction_date"]
        .max()
        .sort_values(ascending=False)
        .index.tolist()
    )
    height = min(520, max(220, 28 * max(6, len(ticker_order))))
    span_days = max(1, int((sub["transaction_date"].max() - sub["transaction_date"].min()).days) + 1)
    date_fmt, tick_n = _ticker_timeline_x_axis_format(span_days)
    points = (
        alt.Chart(sub)
        .mark_circle(size=88, opacity=0.9, stroke="#ffffff", strokeWidth=1)
        .encode(
            x=alt.X(
                "transaction_date:T",
                title="Transaction date",
                axis=alt.Axis(
                    format=date_fmt,
                    tickCount=tick_n,
                    labelColor=THEME["chart_axis_label"],
                    titleColor=THEME["chart_axis_title"],
                ),
            ),
            y=alt.Y(
                "ticker:N",
                sort=ticker_order,
                title="Ticker",
                axis=alt.Axis(labelColor=THEME["chart_axis_label"], titleColor=THEME["chart_axis_title"]),
            ),
            color=alt.Color(
                "txn_type_label:N",
                title="Type",
                scale=alt.Scale(domain=color_domain, range=color_range),
            ),
            tooltip=[
                alt.Tooltip("ticker:N", title="Ticker"),
                alt.Tooltip("transaction_date:T", title="Date", format="%Y-%m-%d"),
                alt.Tooltip("txn_type_label:N", title="Type"),
                alt.Tooltip("amount_range_raw:N", title="Amount"),
            ],
        )
        .properties(height=height)
    )
    return _altair_readability(points)
def build_price_overlay_figure(frame: pd.DataFrame, ticker: str):
    try:
        import plotly.graph_objects as go
    except ImportError:
        return None
    bars = load_polygon_bars(ticker)
    t = str(ticker).strip().upper()
    trades = frame.loc[frame["ticker"].astype(str).str.upper() == t].dropna(subset=["transaction_date"]).copy()
    if bars.empty and trades.empty:
        return None
    fig = go.Figure()
    if not bars.empty:
        bars["date"] = pd.to_datetime(bars["date"], errors="coerce")
        fig.add_trace(
            go.Scatter(
                x=bars["date"],
                y=bars["close"],
                mode="lines",
                name="Close (Polygon cache)",
                line=dict(color=THEME["navy"], width=2),
            )
        )
    if not trades.empty:
        bars_sorted = bars.sort_values("date") if not bars.empty else pd.DataFrame()
        trade_rows: list[dict[str, object]] = []
        for _, row in trades.iterrows():
            td = row["transaction_date"]
            y_val = None
            if not bars_sorted.empty:
                eligible = bars_sorted.loc[bars_sorted["date"] <= td, "close"]
                if not eligible.empty:
                    y_val = float(eligible.iloc[-1])
            if y_val is None and not bars_sorted.empty:
                y_val = float(bars_sorted["close"].iloc[0])
            trade_rows.append(
                {
                    "transaction_date": td,
                    "y": y_val,
                    "member": row["member"],
                    "txn_type_label": transaction_type_display_label(row["transaction_type"]),
                }
            )
        trade_df = pd.DataFrame(trade_rows)
        for lab, g in trade_df.groupby("txn_type_label", observed=True):
            color = _TICKER_TIMELINE_TYPE_COLORS.get(lab, "#64748b")
            fig.add_trace(
                go.Scatter(
                    x=g["transaction_date"],
                    y=g["y"],
                    mode="markers",
                    name=f"Trade · {lab}",
                    marker=dict(size=11, color=color, symbol="diamond", line=dict(width=1, color="#fff")),
                    text=g["member"],
                    hovertemplate="%{text}<br>%{x|%Y-%m-%d}<extra></extra>",
                )
            )
    fig.update_layout(
        height=420,
        paper_bgcolor=THEME["plotly_paper"],
        plot_bgcolor=THEME["plotly_scene_bg"],
        margin=dict(l=40, r=20, t=30, b=60),
        legend=dict(orientation="h", yanchor="top", y=-0.18, x=0),
        xaxis_title="Date",
        yaxis_title="Price (close)" if not bars.empty else "Trade events",
    )
    return fig
