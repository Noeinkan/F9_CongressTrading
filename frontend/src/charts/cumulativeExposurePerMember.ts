import type { TickerCumulativeExposureRow } from "@/api/types";

const TYPE_COLORS: Record<string, string> = {
  Buy: "#15803d",
  Sell: "#be123c",
  "Sell (partial)": "#c2410c",
  Exchange: "#1d4ed8",
  Unknown: "#64748b",
};

export function buildCumulativeExposurePerMemberOption(
  rows: TickerCumulativeExposureRow[],
  members: string[],
): Record<string, unknown> | null {
  if (!rows.length || !members.length) return null;

  const n = members.length;
  const panelHeight = 78;
  const totalHeight = Math.max(240, n * panelHeight);
  const grids: Record<string, unknown>[] = [];
  const xAxes: Record<string, unknown>[] = [];
  const yAxes: Record<string, unknown>[] = [];
  const series: Record<string, unknown>[] = [];

  members.forEach((member, i) => {
    const top = `${Math.round((i / n) * 100)}%`;
    const height = `${Math.round((1 / n) * 100 - 2)}%`;
    grids.push({
      left: 80,
      right: 120,
      top,
      height,
      containLabel: false,
    });
    xAxes.push({
      type: "time",
      gridIndex: i,
      show: i === n - 1,
    });
    yAxes.push({
      type: "value",
      gridIndex: i,
      name: member.length > 28 ? `${member.slice(0, 26)}…` : member,
      nameLocation: "middle",
      nameGap: 50,
      axisLabel: { formatter: (v: number) => `$${v >= 1000 ? `${(v / 1000).toFixed(0)}K` : v}` },
    });

    const memberRows = rows.filter((r) => r.member === member);
    const lineData = memberRows.map((r) => [r.transaction_date, r.cumulative_net]);
    const last = memberRows[memberRows.length - 1];

    series.push({
      name: member,
      type: "line",
      step: "end",
      xAxisIndex: i,
      yAxisIndex: i,
      data: lineData,
      showSymbol: true,
      symbolSize: 6,
      lineStyle: { color: "rgba(40, 55, 75, 0.55)", width: 2 },
      itemStyle: {
        color: (params: { dataIndex: number }) =>
          TYPE_COLORS[memberRows[params.dataIndex]?.txn_type_label ?? "Unknown"] ?? "#64748b",
      },
      markLine: i === 0 ? undefined : undefined,
    });

    if (last) {
      series.push({
        type: "scatter",
        xAxisIndex: i,
        yAxisIndex: i,
        data: [[last.transaction_date, last.cumulative_net]],
        symbolSize: 1,
        label: {
          show: true,
          formatter: last.cumulative_label,
          position: "right",
          fontSize: 11,
          color: "#111820",
        },
        itemStyle: { color: "transparent" },
      });
    }
  });

  return {
    grid: grids,
    xAxis: xAxes,
    yAxis: yAxes,
    series,
    tooltip: {
      trigger: "axis",
      formatter: (params: { seriesName: string; value: [string, number] }[]) => {
        const p = params[0];
        if (!p) return "";
        return `${p.seriesName}<br/>${p.value[0]}<br/>${p.value[1]}`;
      },
    },
    height: totalHeight,
  };
}
