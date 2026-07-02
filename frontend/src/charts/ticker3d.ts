import type { Ticker3DRow } from "@/api/types";

const TYPE_COLORS: Record<string, string> = {
  Buy: "#2f6f4e",
  Sell: "#a64b2a",
  "Sell (partial)": "#c6922b",
  Exchange: "#4a6fa5",
  Unknown: "#64748b",
};

type ScatterPoint = [
  number, // x: timestamp (ms) — time axis
  string, // y: member name — category axis (ECharts matches strings)
  number, // z: log10(amount+1)
  string, // member (tooltip)
  string, // txn type label (tooltip)
  number, // amount_high (tooltip)
];

function dateStringToMs(s: string): number {
  const t = new Date(s).getTime();
  return Number.isFinite(t) ? t : Date.now();
}

function formatAmount(z: number): string {
  const amt = Math.pow(10, z) - 1;
  if (!Number.isFinite(amt)) return "—";
  if (amt >= 1_000_000) return `$${(amt / 1_000_000).toFixed(2)}M`;
  if (amt >= 1_000) return `$${(amt / 1_000).toFixed(1)}k`;
  return `$${amt.toFixed(0)}`;
}

function formatDate(ms: number): string {
  const d = new Date(ms);
  if (!Number.isFinite(d.getTime())) return "";
  return d.toISOString().slice(0, 10);
}

export function buildTicker3DOption(rows: Ticker3DRow[]): Record<string, unknown> | null {
  if (!rows.length) return null;

  // Preserve first-seen order so the Y axis lists members deterministically.
  const members: string[] = [];
  const seen = new Set<string>();
  for (const r of rows) {
    if (!seen.has(r.member)) {
      seen.add(r.member);
      members.push(r.member);
    }
  }

  const types = [...new Set(rows.map((r) => r.txn_type_label))];

  const minZ = Math.min(...rows.map((r) => r.z));
  const maxZ = Math.max(...rows.map((r) => r.z));

  const series = types.map((type) => ({
    name: type,
    type: "scatter3D" as const,
    coordinateSystem: "cartesian3D" as const,
    symbolSize: (val: number[]) => 7 + Math.min(16, Math.max(0, (val[2] ?? 0)) * 1.6),
    itemStyle: {
      color: TYPE_COLORS[type] ?? "#64748b",
      opacity: 0.9,
      borderWidth: 0.5,
      borderColor: "rgba(255,255,255,0.4)",
    },
    emphasis: {
      itemStyle: {
        color: "#ffffff",
        borderColor: TYPE_COLORS[type] ?? "#64748b",
        borderWidth: 2,
        opacity: 1,
      },
    },
    data: rows
      .filter((r) => r.txn_type_label === type)
      .map(
        (r): ScatterPoint => [
          dateStringToMs(r.date),
          r.member,
          r.z,
          r.member,
          r.txn_type_label,
          r.amount_high ?? Math.pow(10, r.z) - 1,
        ],
      ),
  }));

  return {
    backgroundColor: "transparent",
    legend: {
      show: true,
      data: types,
      top: 8,
      left: "center",
      textStyle: { color: "#334155", fontSize: 12 },
      icon: "circle",
      itemWidth: 10,
      itemHeight: 10,
      itemGap: 16,
      type: types.length > 6 ? "scroll" : "plain",
    },
    tooltip: {
      show: true,
      confine: true,
      backgroundColor: "rgba(255,255,255,0.96)",
      borderColor: "#cbd5e1",
      borderWidth: 1,
      textStyle: { color: "#0f172a", fontSize: 12 },
      formatter: (params: { value: ScatterPoint }) => {
        const [ts, member, z, , type] = params.value;
        return `
          <div style="font-weight:600;margin-bottom:4px">${member}</div>
          <div style="color:#475569">${type}</div>
          <div style="color:#475569">${formatDate(ts)}</div>
          <div style="margin-top:4px"><b>${formatAmount(z)}</b> disclosed (high)</div>
        `;
      },
    },
    visualMap: {
      show: true,
      right: 16,
      top: "middle",
      min: Math.floor(minZ),
      max: Math.ceil(maxZ),
      dimension: "z",
      calculable: true,
      realtime: true,
      text: ["$1M+", "$1k"],
      textStyle: { color: "#475569", fontSize: 11 },
      inRange: { symbolSize: [6, 22] },
      itemWidth: 12,
      itemHeight: 140,
      seriesIndex: types.map((_, i) => i),
    },
    grid3D: {
      // Leave room for the legend on top and the visualMap on the right so
      // the chart walls and axis names don't get clipped.
      top: 56,
      bottom: 28,
      left: 80,
      right: 96,
      boxWidth: 240,
      boxDepth: 110,
      boxHeight: 110,
      viewControl: {
        projection: "perspective",
        alpha: 22,
        beta: 35,
        autoRotate: false,
        distance: 260,
        minDistance: 80,
        maxDistance: 600,
        rotateSensitivity: 1.2,
        zoomSensitivity: 1.5,
        panSensitivity: 1,
      },
      light: {
        main: { intensity: 1.3, shadow: true, alpha: 30, beta: 40 },
        ambient: { intensity: 0.5 },
      },
      environment: "auto",
      axisPointer: {
        show: true,
        lineStyle: { color: "#94a3b8", width: 1, type: "dashed", opacity: 0.7 },
        label: {
          show: true,
          backgroundColor: "rgba(15,23,42,0.85)",
          borderColor: "transparent",
          color: "#f8fafc",
          padding: [4, 8],
          borderRadius: 4,
        },
      },
    },
    xAxis3D: {
      type: "time",
      name: "Date",
      nameGap: 22,
      nameTextStyle: { color: "#475569", fontSize: 11 },
      axisLine: { lineStyle: { color: "#cbd5e1" } },
      // ECharts time-axis template tokens — NOT JavaScript Date format.
      axisLabel: {
        color: "#475569",
        fontSize: 10,
        margin: 12,
        hideOverlap: true,
        formatter: {
          year: "{yyyy}",
          month: "{MMM} {yyyy}",
          day: "{MMM} {d}",
          hour: "{HH}:{mm}",
          minute: "{HH}:{mm}",
          second: "{HH}:{mm}:{ss}",
        },
      },
      splitLine: { show: true, lineStyle: { color: "#e2e8f0", type: "dashed" } },
      splitNumber: 6,
    },
    yAxis3D: {
      type: "category",
      data: members,
      name: "Member",
      nameGap: 40,
      nameTextStyle: { color: "#475569", fontSize: 11 },
      axisLine: { lineStyle: { color: "#cbd5e1" } },
      axisLabel: {
        color: "#475569",
        fontSize: 10,
        interval: 0,
        rotate: 0,
        margin: 12,
        hideOverlap: true,
      },
      splitLine: { show: true, lineStyle: { color: "#f1f5f9" } },
    },
    zAxis3D: {
      type: "value",
      name: "log₁₀(amount + 1)",
      nameGap: 32,
      nameTextStyle: { color: "#475569", fontSize: 11 },
      axisLine: { lineStyle: { color: "#cbd5e1" } },
      axisLabel: { color: "#64748b", fontSize: 10, margin: 12 },
      splitLine: { show: true, lineStyle: { color: "#f1f5f9" } },
    },
    series,
  };
}