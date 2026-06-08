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
  const types = [...new Set(rows.map((r) => r.txn_type_label))];
  const series = types.map((type) => ({
    name: type,
    type: "scatter3D",
    symbolSize: 8,
    itemStyle: { color: TYPE_COLORS[type] ?? "#64748b" },
    data: rows
      .filter((r) => r.txn_type_label === type)
      .map((r) => [r.date, r.member, r.z]),
  }));
  return {
    grid3D: { boxWidth: 200, boxDepth: 80, viewControl: { projection: "perspective" } },
    xAxis3D: { type: "time", name: "Date" },
    yAxis3D: { type: "category", data: [...new Set(rows.map((r) => r.member))], name: "Member" },
    zAxis3D: { type: "value", name: "log₁₀(amount+1)" },
    series,
  };
}
