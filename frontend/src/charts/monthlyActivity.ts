export type MonthlyActivityRow = {
  month: string | null;
  transactions: number;
  amount_low: number;
  amount_high: number;
};

export function buildMonthlyActivityOption(rows: MonthlyActivityRow[]): Record<string, unknown> {
  const months = rows.map((r) => (r.month ? String(r.month).slice(0, 7) : ""));
  const counts = rows.map((r) => r.transactions);
  return {
    grid: { left: 48, right: 24, top: 24, bottom: 48 },
    xAxis: { type: "category", data: months },
    yAxis: { type: "value", name: "Transactions" },
    series: [
      {
        type: "line",
        data: counts,
        smooth: true,
        areaStyle: { color: "rgba(32, 52, 74, 0.15)" },
        lineStyle: { color: "#20344a", width: 2 },
        itemStyle: { color: "#20344a" },
      },
    ],
    tooltip: { trigger: "axis" },
  };
}
