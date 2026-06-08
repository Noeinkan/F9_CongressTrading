export type CallPutMonthlyRow = {
  month: string | null;
  option_side: string;
  transactions: number;
};

export function buildCallPutAreaOption(rows: CallPutMonthlyRow[]): Record<string, unknown> | null {
  if (!rows.length) return null;
  const months = [...new Set(rows.map((r) => r.month ?? "").filter(Boolean))].sort();
  const callData = months.map((m) => {
    const row = rows.find((r) => r.month === m && r.option_side === "Call");
    return row?.transactions ?? 0;
  });
  const putData = months.map((m) => {
    const row = rows.find((r) => r.month === m && r.option_side === "Put");
    return row?.transactions ?? 0;
  });
  return {
    grid: { left: 48, right: 24, top: 24, bottom: 48 },
    xAxis: { type: "category", data: months },
    yAxis: { type: "value", name: "Transactions" },
    legend: { bottom: 0 },
    series: [
      { name: "Call", type: "line", stack: "options", areaStyle: {}, data: callData, itemStyle: { color: "#15803d" } },
      { name: "Put", type: "line", stack: "options", areaStyle: {}, data: putData, itemStyle: { color: "#be123c" } },
    ],
    tooltip: { trigger: "axis" },
  };
}
