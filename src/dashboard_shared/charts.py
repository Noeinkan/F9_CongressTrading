from __future__ import annotations

import altair as alt
import numpy as np
import pandas as pd

from .constants import THEME
from .components import _copy
from .formatting import format_currency_compact, format_cumulative_net_label, format_disclosed_range
from .data import (
    load_polygon_bars,
    transaction_type_display_label,
)
from .analytics import signed_trade_notional
from .styles import _altair_readability


def _axis(
    title: str,
    *,
    tick_count: int | None = None,
    grid: bool = False,
    format_spec: str | None = None,
    label_angle: int = 0,
    label_limit: int | None = None,
) -> alt.Axis:
    kw: dict = {
        "title": title,
        "labelColor": THEME["chart_axis_label"],
        "titleColor": THEME["chart_axis_title"],
        "gridColor": THEME["chart_grid_major"],
    }
    if tick_count is not None:
        kw["tickCount"] = tick_count
    if grid:
        kw["grid"] = True
    if format_spec:
        kw["format"] = format_spec
    if label_angle:
        kw["labelAngle"] = label_angle
    if label_limit is not None:
        kw["labelLimit"] = label_limit
    return alt.Axis(**kw)


def _bar_count_labels_horizontal(
    chart_data: pd.DataFrame,
    label_field: str,
    *,
    value_field: str = "transactions",
) -> alt.Chart:
    return (
        alt.Chart(chart_data)
        .mark_text(dx=4, fontSize=12, fontWeight=600, align="left", baseline="middle")
        .encode(
            x=alt.X(f"{value_field}:Q"),
            y=alt.Y(f"{label_field}:N", sort=alt.EncodingSortField(field=value_field, order="descending")),
            text=alt.Text(f"{value_field}:Q", format=",.0f"),
            color=alt.value(THEME["chart_axis_title"]),
        )
    )


def _bar_count_labels_vertical(
    chart_data: pd.DataFrame,
    label_field: str,
    *,
    value_field: str = "transactions",
) -> alt.Chart:
    return (
        alt.Chart(chart_data)
        .mark_text(dy=-8, fontSize=12, fontWeight=600, align="center")
        .encode(
            x=alt.X(f"{label_field}:N"),
            y=alt.Y(f"{value_field}:Q"),
            text=alt.Text(f"{value_field}:Q", format=",.0f"),
            color=alt.value(THEME["chart_axis_title"]),
        )
    )


def _build_time_series_chart(frame: pd.DataFrame) -> alt.Chart:
    chart_data = frame.copy()
    chart_data["month_label"] = chart_data["month"].dt.strftime("%b %Y")
    chart_data["range_label"] = [
        format_disclosed_range(lo, hi)
        for lo, hi in zip(chart_data["amount_low"], chart_data["amount_high"], strict=True)
    ]

    area = (
        alt.Chart(chart_data)
        .mark_area(
            line={"color": THEME["accent"], "strokeWidth": 2.5},
            color=THEME["chart_series_accent_fill"],
            opacity=0.35,
        )
        .encode(
            x=alt.X("month:T", axis=_axis("Calendar month", grid=True, format_spec="%b %Y")),
            y=alt.Y(
                "transactions:Q",
                axis=_axis("Disclosure rows", tick_count=5, grid=True),
            ),
            tooltip=[
                alt.Tooltip("month_label:N", title="Month"),
                alt.Tooltip("transactions:Q", title="Transactions", format=",.0f"),
                alt.Tooltip("range_label:N", title="Disclosed range"),
            ],
        )
    )
    labels = None
    if len(chart_data) <= 18:
        labels = (
            alt.Chart(chart_data)
            .mark_text(dy=-10, fontSize=11, fontWeight=600)
            .encode(
                x="month:T",
                y="transactions:Q",
                text=alt.Text("transactions:Q", format=",.0f"),
                color=alt.value(THEME["chart_axis_title"]),
            )
        )
    base = (area + labels) if labels is not None else area
    return _altair_readability(base.properties(height=300).configure(background="transparent"))


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
    has_range = "amount_low" in chart_data.columns and "amount_high" in chart_data.columns
    if has_range:
        chart_data["range_label"] = [
            format_disclosed_range(lo, hi)
            for lo, hi in zip(chart_data["amount_low"], chart_data["amount_high"], strict=True)
        ]
    y_title = y_axis_title or label_field.replace("_", " ").title()

    tips = [
        alt.Tooltip(f"{label_field}:N", title=title.rstrip("s")),
        alt.Tooltip("transactions:Q", title="Transactions", format=",.0f"),
    ]
    if has_range:
        tips.append(alt.Tooltip("range_label:N", title="Disclosed range"))

    bars = (
        alt.Chart(chart_data)
        .mark_bar(cornerRadiusTopRight=6, cornerRadiusBottomRight=6, color=color)
        .encode(
            x=alt.X("transactions:Q", axis=_axis(title, tick_count=5, grid=True)),
            y=alt.Y(
                f"{label_field}:N",
                sort="-x",
                axis=_axis(y_title, label_limit=220),
            ),
            tooltip=tips,
        )
    )
    labels = _bar_count_labels_horizontal(chart_data, label_field)
    return _altair_readability(
        (bars + labels).properties(height=320).configure(background="transparent")
    )


_NET_BUY_COLOR = THEME["chart_buy"]
_NET_SELL_COLOR = THEME["chart_sell"]


def _aggregate_net_trade_amount(
    frame: pd.DataFrame,
    *,
    top_n: int = 20,
    group_field: str = "ticker",
) -> pd.DataFrame | None:
    """Per-ticker (or group) net signed notional for the current filter slice."""
    if frame.empty or group_field not in frame.columns:
        return None

    work = frame.copy()
    if group_field == "ticker":
        work = work[work["ticker"].astype(str).str.strip() != ""]
    if work.empty:
        return None

    work["_signed"] = work.apply(signed_trade_notional, axis=1)
    signed = pd.to_numeric(work["_signed"], errors="coerce").fillna(0.0)
    work["_buy"] = signed.clip(lower=0.0)
    work["_sell"] = (-signed).clip(lower=0.0)

    agg_spec: dict[str, tuple[str, str]] = {
        "net_amount": ("_signed", "sum"),
        "buy_amount": ("_buy", "sum"),
        "sell_amount": ("_sell", "sum"),
        "trades": (group_field, "size"),
    }
    if "transaction_date" in work.columns:
        agg_spec["first_trade"] = ("transaction_date", "min")
        agg_spec["last_trade"] = ("transaction_date", "max")

    agg = work.groupby(group_field, as_index=False).agg(**agg_spec)
    agg = agg[agg["net_amount"].abs() > 0]
    if agg.empty:
        return None

    agg = agg.reindex(agg["net_amount"].abs().sort_values(ascending=False).index).head(top_n)
    agg = agg.sort_values("net_amount", ascending=False)

    agg["direction"] = np.where(agg["net_amount"] >= 0, "Net buying", "Net selling")
    agg["net_label"] = agg["net_amount"].map(format_currency_compact)
    agg["buy_label"] = agg["buy_amount"].map(format_currency_compact)
    agg["sell_label"] = agg["sell_amount"].map(format_currency_compact)
    if "first_trade" in agg.columns:
        agg["first_trade_label"] = pd.to_datetime(agg["first_trade"], errors="coerce").dt.strftime("%Y-%m-%d")
        agg["last_trade_label"] = pd.to_datetime(agg["last_trade"], errors="coerce").dt.strftime("%Y-%m-%d")
    return agg


def _build_net_trade_amount_chart(
    frame: pd.DataFrame,
    *,
    top_n: int = 20,
    group_field: str = "ticker",
    agg: pd.DataFrame | None = None,
) -> alt.Chart | None:
    """Diverging horizontal bars of net signed trade notional per ticker.

    Positive (net buying) renders green, negative (net selling) renders red, mirroring
    the Capitol-style "Net Trade Amount" view. Respects whatever slice ``frame`` already
    represents (i.e. the active filters).
    """
    if agg is None:
        agg = _aggregate_net_trade_amount(frame, top_n=top_n, group_field=group_field)
    if agg is None or agg.empty:
        return None

    label_title = group_field.replace("_", " ").title()
    sort_order = agg[group_field].tolist()
    height = min(640, max(220, 26 * max(6, len(agg))))

    bars = (
        alt.Chart(agg)
        .mark_bar(cornerRadius=4, height=alt.RelativeBandSize(0.72))
        .encode(
            x=alt.X(
                "net_amount:Q",
                axis=_axis("Net trade amount (signed disclosure range)", tick_count=7, grid=True, format_spec="$~s"),
            ),
            y=alt.Y(
                f"{group_field}:N",
                sort=sort_order,
                axis=_axis(label_title, label_limit=220),
            ),
            color=alt.Color(
                "direction:N",
                title="Direction",
                scale=alt.Scale(
                    domain=["Net buying", "Net selling"],
                    range=[_NET_BUY_COLOR, _NET_SELL_COLOR],
                ),
                legend=alt.Legend(
                    orient="bottom",
                    direction="horizontal",
                    labelColor=THEME["chart_legend_label"],
                    titleColor=THEME["chart_legend_title"],
                    symbolType="square",
                ),
            ),
            tooltip=[
                alt.Tooltip(f"{group_field}:N", title=label_title),
                alt.Tooltip("net_label:N", title="Net amount"),
                alt.Tooltip("buy_label:N", title="Gross buying"),
                alt.Tooltip("sell_label:N", title="Gross selling"),
                alt.Tooltip("trades:Q", title="Trades", format=",.0f"),
                *(
                    [
                        alt.Tooltip("first_trade_label:N", title="First trade"),
                        alt.Tooltip("last_trade_label:N", title="Last trade"),
                    ]
                    if "first_trade_label" in agg.columns
                    else []
                ),
            ],
        )
    )
    def _net_value_labels(*, positive: bool) -> alt.Chart:
        return (
            alt.Chart(agg)
            .transform_filter(
                alt.datum.net_amount >= 0 if positive else alt.datum.net_amount < 0
            )
            .mark_text(
                dx=4 if positive else -4,
                align="left" if positive else "right",
                fontSize=11,
                fontWeight=600,
                baseline="middle",
            )
            .encode(
                x=alt.X("net_amount:Q"),
                y=alt.Y(f"{group_field}:N", sort=sort_order),
                text=alt.Text("net_label:N"),
                color=alt.value(THEME["chart_axis_title"]),
            )
        )

    value_labels = _net_value_labels(positive=True) + _net_value_labels(positive=False)
    return _altair_readability(
        (bars + value_labels).properties(height=height).configure(background="transparent")
    )


def _build_mix_chart(
    frame: pd.DataFrame,
    label_field: str,
    *,
    color: str,
    x_axis_title: str | None = None,
) -> alt.Chart:
    chart_data = frame.copy()
    x_title = x_axis_title or label_field.replace("_", " ").title()
    bars = (
        alt.Chart(chart_data)
        .mark_bar(cornerRadiusTopLeft=8, cornerRadiusTopRight=8, color=color)
        .encode(
            x=alt.X(
                f"{label_field}:N",
                axis=_axis(x_title, label_angle=-25, label_limit=180),
            ),
            y=alt.Y("transactions:Q", axis=_axis("Row count", tick_count=4, grid=True)),
            tooltip=[
                alt.Tooltip(f"{label_field}:N", title=label_field.replace("_", " ").title()),
                alt.Tooltip("transactions:Q", title="Transactions", format=",.0f"),
            ],
        )
    )
    labels = _bar_count_labels_vertical(chart_data, label_field)
    return _altair_readability(
        (bars + labels).properties(height=250).configure(background="transparent")
    )


_TICKER_TIMELINE_TYPE_COLORS: dict[str, str] = {
    "Buy": THEME["chart_buy"],
    "Sell": THEME["chart_sell"],
    "Sell (partial)": THEME["chart_sell_partial"],
    "Exchange": THEME["chart_exchange"],
    "Unknown": THEME["chart_unknown"],
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


def _timeline_date_range_label(series: pd.Series) -> str:
    t0 = pd.Timestamp(series.min())
    t1 = pd.Timestamp(series.max())
    span_days = max(1, int((t1 - t0).days) + 1)
    if span_days <= 45:
        fmt = "%d %b %Y"
    elif span_days <= 550:
        fmt = "%b %Y"
    else:
        fmt = "%Y"
    return f"{t0.strftime(fmt)} – {t1.strftime(fmt)}"


def _ticker_timeline_x_axis_for_series(series: pd.Series) -> alt.Axis:
    span_days = max(1, int((series.max() - series.min()).days) + 1)
    date_fmt, _tick_n = _ticker_timeline_x_axis_format(span_days)
    tick_values = _ticker_timeline_vertical_rule_dates(series).tolist()
    range_label = _timeline_date_range_label(series)
    label_angle = -35 if span_days <= 45 and len(tick_values) > 8 else 0
    return alt.Axis(
        title=f"Transaction date ({range_label})",
        format=date_fmt,
        values=tick_values,
        labelAngle=label_angle,
        labelOverlap=False,
        labelColor=THEME["chart_axis_label"],
        titleColor=THEME["chart_axis_title"],
        labelFontSize=14,
        titleFontSize=15,
        titleFontWeight="bold",
        labelFontWeight=600,
        labelPadding=8,
        titlePadding=14,
        grid=True,
        gridColor=THEME["chart_grid_major"],
        gridDash=[2, 3],
        domainColor=THEME["chart_axis_title"],
        tickColor=THEME["chart_axis_label"],
        tickSize=7,
        domainWidth=1.5,
    )


def _finalize_timeline_scatter(base: alt.LayerChart | alt.Chart, height: int) -> alt.Chart:
    chart = (
        base.properties(height=height)
        .configure(background="transparent")
        .configure(padding={"bottom": 72, "top": 8, "left": 8, "right": 12})
    )
    return _altair_readability(chart)


def _cumulative_exposure_guide_html(ticker: str) -> str:
    t = str(ticker).strip().upper() or "—"
    border = THEME["accent"]
    bg = "rgba(255, 252, 246, 0.98)"
    text = THEME["ui_caption"]
    return (
        f'<div style="margin:0.35rem 0 0.85rem 0;padding:0.85rem 1rem;border-left:4px solid {border};'
        f'background:{bg};border-radius:0 8px 8px 0;font-size:0.92rem;color:{text};line-height:1.45;">'
        f'<p style="margin:0 0 0.45rem 0;font-weight:600;font-size:0.98rem;color:{THEME["chart_axis_title"]};">'
        f'{_copy("cumulative_exposure_guide_title")} · <span style="font-weight:700;">{t}</span></p>'
        f'<p style="margin:0 0 0.45rem 0;">{_copy("cumulative_exposure_lede")}</p>'
        f'<p style="margin:0 0 0.45rem 0;">{_copy("cumulative_exposure_guide_lines")}</p>'
        f'<p style="margin:0;font-size:0.86rem;opacity:0.92;">{_copy("cumulative_exposure_guide_note")}</p>'
        f"</div>"
    )


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
    x_axis = _ticker_timeline_x_axis_for_series(sub["transaction_date"])
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
            x=alt.X(
                "transaction_date:T",
                axis=x_axis,
                scale=alt.Scale(nice=False, padding=16),
            ),
            y=alt.Y("member:N", sort=member_order, axis=y_axis),
            color=alt.Color(
                "txn_type_label:N",
                scale=alt.Scale(domain=color_domain, range=color_range),
                legend=None,
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
    return _finalize_timeline_scatter(vlines + points, height)


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
    hi = pd.to_numeric(sub["amount_high"], errors="coerce").fillna(0.0)
    sub["_z"] = np.log10(hi.clip(lower=0.0) + 1.0)
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
                    "z = log₁₀(high+1): %{z:.2f}<br>"
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
                title=dict(text="log₁₀(amount high + 1)", font=axis_title),
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


def _member_facet_label(name: object) -> str:
    s = "" if name is None or (isinstance(name, float) and pd.isna(name)) else str(name).strip()
    for prefix in ("Hon. ", "Hon ", "Rep. ", "Sen. "):
        if s.startswith(prefix):
            return s[len(prefix) :].strip()
    return s or "—"


def _dedupe_cumulative_trades(sub: pd.DataFrame) -> pd.DataFrame:
    keys = [
        c
        for c in ("member", "transaction_date", "transaction_type", "amount_low", "amount_high", "filing_date")
        if c in sub.columns
    ]
    if not keys:
        return sub
    return sub.drop_duplicates(subset=keys, keep="first")


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

    sub = _dedupe_cumulative_trades(sub)
    sub["_signed"] = sub.apply(signed_trade_notional, axis=1)
    member_counts = sub["member"].value_counts()
    member_order = member_counts.head(top_n).index.tolist()
    sub = sub[sub["member"].isin(member_order)]
    if sub.empty:
        return None, []

    label_map = {m: _member_facet_label(m) for m in member_order}
    sub["member_label"] = sub["member"].map(label_map)

    sub = sub.sort_values(["member", "transaction_date", "filing_date"], ascending=[True, True, True])
    sub["cumulative_usd"] = sub.groupby("member", observed=True)["_signed"].cumsum()
    sub["trade_date_label"] = sub["transaction_date"].dt.strftime("%Y-%m-%d")
    sub["txn_type_label"] = sub["transaction_type"].map(transaction_type_display_label)
    sub["cumulative_label"] = sub["cumulative_usd"].map(format_currency_compact)
    sub["trade_effect_label"] = sub.apply(
        lambda r: (
            f"+{format_currency_compact(r['_signed'])} buy"
            if float(r["_signed"]) > 0
            else (
                f"{format_currency_compact(r['_signed'])} sell"
                if float(r["_signed"]) < 0
                else "No $ change"
            )
        ),
        axis=1,
    )

    n_members = len(member_order)
    panel_height = 78
    span_days = max(1, int((sub["transaction_date"].max() - sub["transaction_date"].min()).days) + 1)
    date_fmt, tick_n = _ticker_timeline_x_axis_format(span_days)
    x_max = pd.Timestamp(sub["transaction_date"].max())
    x_min = pd.Timestamp(sub["transaction_date"].min())
    label_x = x_max + pd.Timedelta(days=max(5, span_days // 12))

    last_idx = sub.groupby("member", observed=True).tail(1).index
    sub["is_last_trade"] = sub.index.isin(last_idx)
    sub["end_label"] = np.where(
        sub["is_last_trade"],
        sub["cumulative_usd"].map(format_cumulative_net_label),
        "",
    )
    sub["label_x"] = np.where(sub["is_last_trade"], label_x, pd.NaT)

    preferred = ["Buy", "Sell", "Sell (partial)", "Exchange", "Unknown"]
    present = sub["txn_type_label"].drop_duplicates().tolist()
    color_domain = [x for x in preferred if x in present] + sorted(x for x in present if x not in preferred)
    color_range = [_TICKER_TIMELINE_TYPE_COLORS.get(x, "#64748b") for x in color_domain]

    x_axis = alt.Axis(
        format=date_fmt,
        tickCount=tick_n,
        labelAngle=-24,
        labelOverlap=False,
        labelColor=THEME["chart_axis_label"],
        titleColor=THEME["chart_axis_title"],
        gridColor=THEME["chart_grid_major"],
    )
    y_axis = alt.Axis(
        labelColor=THEME["chart_axis_label"],
        titleColor=THEME["chart_axis_title"],
        tickCount=4,
        gridColor=THEME["chart_grid_major"],
        format="$~s",
    )
    x_scale = alt.Scale(domain=[x_min, label_x], nice=False)
    facet_labels = [label_map[m] for m in member_order]
    facet_row = alt.Row(
        "member_label:N",
        sort=facet_labels,
        header=alt.Header(
            title=None,
            labelAngle=0,
            labelAlign="left",
            labelFontSize=13,
            labelFontWeight=600,
            labelColor=THEME["chart_axis_title"],
        ),
    )

    x_enc = alt.X(
        "transaction_date:T",
        title="When the trade happened",
        axis=x_axis,
        scale=x_scale,
    )
    y_enc = alt.Y(
        "cumulative_usd:Q",
        title="Running net $",
        axis=y_axis,
    )
    tooltips = [
        alt.Tooltip("member:N", title="Member"),
        alt.Tooltip("trade_date_label:N", title="Trade date"),
        alt.Tooltip("txn_type_label:N", title="Disclosure type"),
        alt.Tooltip("trade_effect_label:N", title="This trade"),
        alt.Tooltip("cumulative_label:N", title="Running total after"),
        alt.Tooltip("amount_range_raw:N", title="Reported $ range"),
    ]

    base = alt.Chart(sub)
    zero_line = base.encode(x=x_enc).mark_rule(
        color="rgba(32, 52, 74, 0.38)",
        strokeWidth=1.5,
        strokeDash=[6, 5],
    ).encode(y=alt.datum(0))

    lines = base.encode(x=x_enc, y=y_enc).mark_line(
        color="rgba(40, 55, 75, 0.55)",
        strokeWidth=2,
        interpolate="step-after",
    )

    points = base.encode(x=x_enc, y=y_enc, tooltip=tooltips).mark_circle(
        size=72,
        opacity=0.95,
        stroke="#ffffff",
        strokeWidth=1.2,
    ).encode(
        color=alt.Color(
            "txn_type_label:N",
            title="Trade type",
            scale=alt.Scale(domain=color_domain, range=color_range),
            legend=alt.Legend(
                orient="bottom",
                direction="horizontal",
                titleFontSize=13,
                labelFontSize=12,
                labelColor=THEME["chart_legend_label"],
                titleColor=THEME["chart_legend_title"],
                symbolSize=70,
                padding=8,
            ),
        ),
    )

    end_labels = (
        base.transform_filter(alt.FieldEqualPredicate(field="is_last_trade", equal=True))
        .encode(
            x=alt.X("label_x:T", axis=None, scale=x_scale),
            y=y_enc,
            text=alt.Text("end_label:N"),
        )
        .mark_text(align="left", dx=6, fontSize=11, fontWeight=600, color=THEME["chart_axis_title"])
    )

    layer = (
        alt.layer(zero_line, lines, points, end_labels)
        .resolve_scale(y="independent", x="shared")
        .properties(height=panel_height)
    )

    chart = (
        layer.facet(row=facet_row)
        .properties(
            title={
                "text": f"{t}: net disclosed buy vs sell by member",
                "subtitle": "Each row is one member — flat segments mean no new trades in that period",
                "fontSize": 16,
                "subtitleFontSize": 12,
                "color": THEME["chart_axis_title"],
                "subtitleColor": THEME["ui_caption"],
            },
        )
        .configure(
            background="transparent",
            padding={"bottom": 72, "top": 8, "left": 4, "right": 12},
            view={
                "fill": THEME["chart_view_fill"],
                "stroke": THEME["chart_view_stroke"],
                "strokeWidth": 1,
            },
        )
    )
    return _altair_readability(chart), member_order

def _build_member_activity_timeline(
    frame: pd.DataFrame, member: str, *, top_n: int = 25
) -> tuple[alt.Chart | None, str | None]:
    sub = frame.loc[frame["member"].astype(str) == str(member)].copy()
    sub = sub.dropna(subset=["transaction_date"])
    sub = sub[sub["ticker"].astype(str).str.strip() != ""]
    if sub.empty:
        return None, None
    truncate_note: str | None = None
    ticker_counts = sub.groupby("ticker", observed=True).size().sort_values(ascending=False)
    total_tickers = len(ticker_counts)
    if total_tickers > top_n:
        keep = ticker_counts.head(top_n).index.tolist()
        sub = sub.loc[sub["ticker"].isin(keep)]
        truncate_note = (
            f"Showing the {top_n} most-traded tickers ({total_tickers} total in this slice). "
            "See **By ticker** above for the full breakdown."
        )
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
    height = min(680, max(240, 34 * max(6, len(ticker_order))))
    x_axis = _ticker_timeline_x_axis_for_series(sub["transaction_date"])
    y_axis = alt.Axis(
        title="Ticker (most recent activity at top)",
        labelColor=THEME["chart_axis_label"],
        titleColor=THEME["chart_axis_title"],
        labelFontSize=12,
        labelLimit=120,
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
            x=alt.X(
                "transaction_date:T",
                axis=x_axis,
                scale=alt.Scale(nice=False, padding=16),
            ),
            y=alt.Y("ticker:N", sort=ticker_order, axis=y_axis),
            color=alt.Color(
                "txn_type_label:N",
                scale=alt.Scale(domain=color_domain, range=color_range),
                legend=None,
            ),
            tooltip=[
                alt.Tooltip("ticker:N", title="Ticker"),
                alt.Tooltip("transaction_date:T", title="Date", format="%Y-%m-%d"),
                alt.Tooltip("txn_type_label:N", title="Type"),
                alt.Tooltip("transaction_type:N", title="Raw code"),
                alt.Tooltip("amount_range_raw:N", title="Amount range"),
                alt.Tooltip("issuer_name:N", title="Issuer"),
            ],
        )
    )
    return _finalize_timeline_scatter(vlines + points, height), truncate_note


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
    axis_title = dict(color=THEME["plotly_axis_ink"], size=14)
    tick_font = dict(color=THEME["plotly_tick_ink"], size=12)
    fig.update_layout(
        height=420,
        paper_bgcolor=THEME["plotly_paper"],
        plot_bgcolor=THEME["plotly_scene_bg"],
        margin=dict(l=48, r=20, t=36, b=72),
        font=dict(color=THEME["plotly_legend_ink"], size=13),
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.22,
            x=0,
            title=dict(text="Series", font=dict(size=13, color=THEME["plotly_legend_ink"])),
        ),
        xaxis=dict(
            title=dict(text="Date", font=axis_title),
            tickfont=tick_font,
            gridcolor=THEME["chart_grid_major"],
            showgrid=True,
        ),
        yaxis=dict(
            title=dict(
                text="Close price (USD)" if not bars.empty else "Trade events",
                font=axis_title,
            ),
            tickfont=tick_font,
            tickformat="$,.2f" if not bars.empty else None,
            gridcolor=THEME["chart_grid_major"],
            showgrid=True,
        ),
    )
    return fig


def _build_option_side_area_chart(frame: pd.DataFrame) -> alt.Chart:
    chart = (
        alt.Chart(frame)
        .mark_area(opacity=0.55)
        .encode(
            x=alt.X("month:T", axis=_axis("Month", grid=True, format_spec="%b %Y")),
            y=alt.Y("transactions:Q", axis=_axis("Option trades", tick_count=5, grid=True), stack="zero"),
            color=alt.Color(
                "option_side:N",
                title="Side",
                scale=alt.Scale(
                    domain=["Call", "Put"],
                    range=[THEME["chart_buy"], THEME["chart_sell"]],
                ),
                legend=alt.Legend(
                    orient="bottom",
                    direction="horizontal",
                    labelColor=THEME["chart_legend_label"],
                    titleColor=THEME["chart_legend_title"],
                ),
            ),
            tooltip=[
                alt.Tooltip("month:T", title="Month", format="%b %Y"),
                alt.Tooltip("option_side:N", title="Side"),
                alt.Tooltip("transactions:Q", title="Trades", format=",.0f"),
            ],
        )
        .properties(height=300)
        .configure(background="transparent")
    )
    return _altair_readability(chart)


def _build_call_put_ratio_chart(frame: pd.DataFrame) -> alt.Chart:
    chart = (
        alt.Chart(frame)
        .mark_line(point=True, strokeWidth=2.5, color=THEME["accent"])
        .encode(
            x=alt.X("month:T", axis=_axis("Month", grid=True, format_spec="%b %Y")),
            y=alt.Y("call_put_ratio:Q", axis=_axis("Call ÷ put ratio", tick_count=5, grid=True)),
            tooltip=[
                alt.Tooltip("month:T", title="Month", format="%b %Y"),
                alt.Tooltip("call_put_ratio:Q", title="Ratio", format=".2f"),
            ],
        )
        .properties(height=240)
        .configure(background="transparent")
    )
    return _altair_readability(chart)
