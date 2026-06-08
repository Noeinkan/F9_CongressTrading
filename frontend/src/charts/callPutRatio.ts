export type CallPutRatioRow = {
  month: string | null;
  call: number;
  put: number;
  call_put_ratio: number;
};

export function buildCallPutRatioOption(rows: CallPutRatioRow[]): Record<string, unknown> | null {
  if (!rows.length) return null;
  const months = rows.map((r) => r.month ?? "");
  const ratios = rows.map((r) => r.call_put_ratio);
  return {
    grid: { left: 48, right: 24, top: 24, bottom: 48 },
    xAxis: { type: "category", data: months },
    yAxis: { type: "value", name: "Call ÷ Put" },
    series: [
      {
        name: "Call/Put ratio",
        type: "line",
        data: ratios,
        itemStyle: { color: "#20344a" },
        markLine: {
          silent: true,
          data: [{ yAxis: 1, lineStyle: { type: "dashed", color: "#64748b" } }],
        },
      },
    ],
    tooltip: {
      trigger: "axis",
      formatter: (params: { dataIndex: number }[]) => {
        const i = params[0]?.dataIndex ?? 0;
        const row = rows[i];
        if (!row) return "";
        return `${row.month}<br/>Call: ${row.call}<br/>Put: ${row.put}<br/>Ratio: ${row.call_put_ratio.toFixed(2)}`;
      },
    },
  };
}
