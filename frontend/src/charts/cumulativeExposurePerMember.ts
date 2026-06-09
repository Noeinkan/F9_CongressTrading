import type { TickerCumulativeExposureRow } from "@/api/types";

// Per-transaction-type colors (kept consistent with the rest of the dashboard:
// tickerTimeline.ts / priceOverlay.ts).
const TYPE_COLORS: Record<string, string> = {
  Buy: "#15803d",
  Sell: "#be123c",
  "Sell (partial)": "#c2410c",
  Exchange: "#1d4ed8",
  Unknown: "#64748b",
};

// Per-member accent palette. Each member gets one hue used to label their row
// (left swatch, end-of-line value) so the eye can pair the row with the name
// even when the step line itself is muted.
const MEMBER_PALETTE = [
  "#0ea5e9", // sky
  "#f59e0b", // amber
  "#10b981", // emerald
  "#a855f7", // violet
  "#ef4444", // red
  "#14b8a6", // teal
  "#f97316", // orange
  "#6366f1", // indigo
  "#84cc16", // lime
  "#ec4899", // pink
  "#06b6d4", // cyan
  "#eab308", // yellow
  "#8b5cf6", // purple
  "#22c55e", // green
  "#0f766e", // dark teal
  "#dc2626", // dark red
];

function memberColor(index: number): string {
  return MEMBER_PALETTE[index % MEMBER_PALETTE.length] ?? "#94a3b8";
}

function compactCurrency(v: number): string {
  if (v === 0) return "$0";
  const abs = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  if (abs >= 1_000_000) return `${sign}$${(abs / 1_000_000).toFixed(abs >= 10_000_000 ? 0 : 1)}M`;
  if (abs >= 1_000) return `${sign}$${Math.round(abs / 1_000)}K`;
  return `${sign}$${abs}`;
}

function shortName(name: string, max = 26): string {
  const safe = name ?? "";
  if (safe.length <= max) return safe;
  return `${safe.slice(0, max - 1)}…`;
}

export type CumulativeExposurePerMemberMeta = {
  members: string[];
  memberColors: string[];
  typeColors: Record<string, string>;
  types: string[];
};

export function buildCumulativeExposurePerMemberOption(
  rows: TickerCumulativeExposureRow[],
  members: string[],
): Record<string, unknown> | null {
  if (!rows.length || !members.length) return null;

  const n = members.length;
  const panelHeight = 96;
  const totalHeight = Math.max(280, n * panelHeight + 32);

  const memberColorMap: Record<string, string> = {};
  members.forEach((m, i) => {
    memberColorMap[m] = memberColor(i);
  });

  const grids: Record<string, unknown>[] = [];
  const xAxes: Record<string, unknown>[] = [];
  const yAxes: Record<string, unknown>[] = [];
  const series: Record<string, unknown>[] = [];

  // All panels share the same x-domain so the step lines align vertically.
  const firstDate = rows.reduce(
    (acc, r) => (acc == null || r.transaction_date < acc ? r.transaction_date : acc),
    null as string | null,
  );
  const lastDate = rows.reduce(
    (acc, r) => (acc == null || r.transaction_date > acc ? r.transaction_date : acc),
    null as string | null,
  );

  members.forEach((member, i) => {
    const top = `${Math.round((i / n) * 100)}%`;
    const height = `${Math.round((1 / n) * 100 - 1.5)}%`;
    const accent = memberColorMap[member];
    const isFirst = i === 0;
    const isLast = i === n - 1;

    grids.push({
      left: 168,
      right: 124,
      top,
      height,
      containLabel: false,
    });

    xAxes.push({
      type: "time",
      gridIndex: i,
      show: isLast,
      min: firstDate ?? undefined,
      max: lastDate ?? undefined,
      axisLabel: {
        fontSize: 11,
        color: "#475569",
        hideOverlap: true,
      },
      axisLine: { show: isLast, lineStyle: { color: "#cbd5e1" } },
      axisTick: { show: isLast },
    });

    yAxes.push({
      type: "value",
      gridIndex: i,
      name: shortName(member, 22),
      nameLocation: "middle",
      nameGap: 92,
      nameTextStyle: {
        color: accent,
        fontSize: 12,
        fontWeight: 600,
        align: "left",
        padding: [0, 0, 0, 4],
      },
      axisLabel: {
        fontSize: 10,
        color: "#64748b",
        formatter: (v: number) => compactCurrency(v),
        hideOverlap: true,
      },
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: {
        show: i === 0, // only draw the first panel's grid lines; keeps the chart airy
        lineStyle: { color: "#e2e8f0", type: "dashed" },
      },
    });

    const memberRows = rows
      .filter((r) => r.member === member)
      .sort((a, b) => (a.transaction_date < b.transaction_date ? -1 : 1));
    const lineData = memberRows.map((r) => [r.transaction_date, r.cumulative_net]);

    // Stepped cumulative line, muted but tinted with the member accent.
    series.push({
      name: member,
      type: "line",
      step: "end",
      xAxisIndex: i,
      yAxisIndex: i,
      data: lineData,
      showSymbol: false,
      lineStyle: { color: accent, width: 1.75, opacity: 0.85 },
      z: 2,
      animationDuration: 250,
    });

    // Per-transaction markers: bigger, white-bordered, colored by txn type.
    // This is the main "step up = buy, step down = sell" visual cue.
    if (memberRows.length) {
      const markerData = memberRows.map((r, idx) => ({
        name: r.txn_type_label ?? "Trade",
        value: [r.transaction_date, r.cumulative_net],
        itemStyle: {
          color: TYPE_COLORS[r.txn_type_label ?? "Unknown"] ?? "#64748b",
          borderColor: "#ffffff",
          borderWidth: 1.5,
        },
        // The very first marker for each member is hollow — anchors the start
        // of the line and matches the dashed "$0 start" framing.
        symbol:
          idx === 0 && memberRows.length > 1
            ? "circle"
            : memberRows.length > 1
              ? "circle"
              : "circle",
        symbolSize: idx === 0 ? 7 : 6,
      }));
      series.push({
        name: `${member} · trades`,
        type: "scatter",
        xAxisIndex: i,
        yAxisIndex: i,
        data: markerData,
        symbolSize: 7,
        z: 3,
        itemStyle: { borderColor: "#ffffff", borderWidth: 1.5 },
        emphasis: { scale: 1.4 },
        tooltip: {
          // Per-marker tooltip is configured at series level (axis trigger
          // would be confusing with stacked panels).
          show: true,
        },
      });
    }

    const last = memberRows[memberRows.length - 1];
    if (last) {
      // End-of-row value pill: colored dot + compact net label.
      series.push({
        type: "scatter",
        xAxisIndex: i,
        yAxisIndex: i,
        data: [[last.transaction_date, last.cumulative_net]],
        symbolSize: 1,
        z: 4,
        label: {
          show: true,
          formatter: () =>
            `{dot|${""}}{label| ${last.cumulative_label ?? compactCurrency(last.cumulative_net)} }`,
          position: "right",
          distance: 8,
          rich: {
            dot: {
              color: accent,
              fontSize: 10,
              padding: [0, 2, 0, 0],
            },
            label: {
              color: "#0f172a",
              fontSize: 11,
              fontWeight: 600,
              backgroundColor: "rgba(255,255,255,0.85)",
              borderColor: "#e2e8f0",
              borderWidth: 1,
              borderRadius: 3,
              padding: [2, 6, 2, 4],
            },
          },
        },
        itemStyle: { color: "transparent" },
      });
    }

    // Dashed $0 reference line on the top panel — referenced by the "How to
    // read this chart" copy but never actually drawn before.
    if (isFirst) {
      series.push({
        type: "line",
        xAxisIndex: i,
        yAxisIndex: i,
        markLine: {
          symbol: "none",
          silent: true,
          label: {
            show: true,
            position: "insideEndTop",
            color: "#94a3b8",
            fontSize: 10,
            formatter: "$0",
          },
          lineStyle: { color: "#94a3b8", type: "dashed", width: 1 },
          data: [{ yAxis: 0 }],
        },
      });
    }
  });

  // Panel dividers are implied by grid alignment + the member-color band on
  // the y-axis name; drawing explicit lines per panel would crowd the view.

  return {
    grid: grids,
    xAxis: xAxes,
    yAxis: yAxes,
    series,
    tooltip: {
      trigger: "item",
      backgroundColor: "rgba(15, 23, 42, 0.95)",
      borderColor: "transparent",
      textStyle: { color: "#f8fafc", fontSize: 12 },
      extraCssText: "box-shadow: 0 4px 14px rgba(15, 23, 42, 0.2); border-radius: 6px;",
      formatter: (params: {
        seriesName?: string;
        name?: string;
        value: [string, number] | number;
        data?: { name?: string; value?: [string, number] };
        color?: string;
      }) => {
        const date =
          (Array.isArray(params.value) ? params.value[0] : params.data?.value?.[0]) ??
          params.name ??
          "";
        const net = Array.isArray(params.value)
          ? params.value[1]
          : (params.data?.value?.[1] ?? 0);
        const member = (params.seriesName ?? "").replace(/ · trades$/, "");
        const type = params.data?.name ?? "";
        const typeColor = TYPE_COLORS[type] ?? "#94a3b8";
        return `
          <div style="font-weight:600;margin-bottom:2px;">${member}</div>
          <div style="opacity:0.8;font-size:11px;margin-bottom:4px;">${date}</div>
          <div style="display:flex;align-items:center;gap:6px;">
            <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${typeColor};"></span>
            <span>${type}</span>
          </div>
          <div style="margin-top:4px;font-weight:600;">${compactCurrency(net)} net</div>
        `;
      },
    },
    height: totalHeight,
    animationDuration: 400,
  };
}

export function getCumulativeExposurePerMemberMeta(
  members: string[],
  rows: TickerCumulativeExposureRow[],
): CumulativeExposurePerMemberMeta {
  const memberColors = members.map((_, i) => memberColor(i));
  const types = [...new Set(rows.map((r) => r.txn_type_label ?? "Unknown"))];
  return { members, memberColors, typeColors: TYPE_COLORS, types };
}
