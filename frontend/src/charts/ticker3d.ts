import type { Ticker3DRow } from "@/api/types";

const TYPE_COLORS: Record<string, string> = {
  Buy: "#2f6f4e",
  Sell: "#a64b2a",
  "Sell (partial)": "#c6922b",
  Exchange: "#4a6fa5",
  Unknown: "#64748b",
};

export function buildTicker3DOption(rows: Ticker3DRow[]): Record<string, unknown> | null {
  if (!rows.length) return null;

  const members = [...new Set(rows.map((r) => r.member))];
  const memberIndex = new Map(members.map((m, i) => [m, i]));

  const types = [...new Set(rows.map((r) => r.txn_type_label))];

  const series = types.map((type) => ({
    name: type,
    type: "scatter3D",
    symbolSize: (val: number[]) => 6 + Math.min(14, (val[2] ?? 0) * 1.4),
    itemStyle: { color: TYPE_COLORS[type] ?? "#64748b", opacity: 0.9 },
    data: rows
      .filter((r) => r.txn_type_label === type)
      .map((r) => [r.date, memberIndex.get(r.member) ?? 0, r.z, r.member, r.txn_type_label]),
  }));

  return {
    legend: {
      show: true,
      data: types,
      top: 0,
      left: "center",
      textStyle: { color: "#334155" },
      icon: "circle",
    },
    tooltip: {
      show: true,
      confine: true,
      formatter: (params: { value: [string, number, number, string, string] }) => {
        const [date, , z, member, type] = params.value;
        const amt = Math.pow(10, z) - 1;
        const fmt = amt >= 1_000_000
          ? `$${(amt / 1_000_000).toFixed(2)}M`
          : amt >= 1_000
            ? `$${(amt / 1_000).toFixed(1)}k`
            : `$${amt.toFixed(0)}`;
        return `<b>${member}</b><br/>${date}<br/>${type} · ${fmt}`;
      },
    },
    grid3D: {
      boxWidth: 220,
      boxDepth: 90,
      viewControl: {
        projection: "perspective",
        alpha: 25,
        beta: 30,
        autoRotate: false,
        distance: 220,
      },
      light: { main: { intensity: 1.2 }, ambient: { intensity: 0.4 } },
    },
    xAxis3D: { type: "time", name: "Date", nameGap: 20 },
    yAxis3D: { type: "category", data: members, name: "Member", nameGap: 30 },
    zAxis3D: { type: "value", name: "log₁₀(amount+1)", nameGap: 30 },
    series,
  };
}
