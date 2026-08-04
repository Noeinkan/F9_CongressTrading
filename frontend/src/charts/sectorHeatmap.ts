export type SectorMonthlyRow = {
  month: string | null;
  sector: string;
  transactions: number;
};

function monthLabel(raw: string | null | undefined): string {
  if (!raw) return "";
  return String(raw).slice(0, 7);
}

/** Build an ECharts heatmap option: months on x, sectors on y, trade count as value. */
export function buildSectorHeatmapOption(
  rows: SectorMonthlyRow[],
): Record<string, unknown> | null {
  if (!rows.length) return null;

  const months = [
    ...new Set(rows.map((r) => monthLabel(r.month)).filter(Boolean)),
  ].sort();
  if (!months.length) return null;

  const sectorTotals = new Map<string, number>();
  for (const row of rows) {
    const sector = String(row.sector || "").trim();
    if (!sector) continue;
    sectorTotals.set(sector, (sectorTotals.get(sector) ?? 0) + Number(row.transactions || 0));
  }
  const sectors = [...sectorTotals.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([sector]) => sector);
  if (!sectors.length) return null;

  const countByKey = new Map<string, number>();
  for (const row of rows) {
    const month = monthLabel(row.month);
    const sector = String(row.sector || "").trim();
    if (!month || !sector) continue;
    countByKey.set(`${month}\0${sector}`, Number(row.transactions || 0));
  }

  const data: [number, number, number][] = [];
  let maxVal = 0;
  for (let yi = 0; yi < sectors.length; yi += 1) {
    for (let xi = 0; xi < months.length; xi += 1) {
      const value = countByKey.get(`${months[xi]}\0${sectors[yi]}`) ?? 0;
      data.push([xi, yi, value]);
      if (value > maxVal) maxVal = value;
    }
  }

  const height = Math.max(240, sectors.length * 22 + 80);

  return {
    grid: { left: 140, right: 48, top: 16, bottom: 56 },
    xAxis: {
      type: "category",
      data: months,
      splitArea: { show: true },
      axisLabel: { rotate: months.length > 8 ? 30 : 0 },
    },
    yAxis: {
      type: "category",
      data: sectors,
      axisLabel: { width: 120, overflow: "truncate" },
      splitArea: { show: true },
    },
    visualMap: {
      min: 0,
      max: Math.max(1, maxVal),
      calculable: true,
      orient: "horizontal",
      left: "center",
      bottom: 0,
      inRange: { color: ["#eef2f6", "#20344a"] },
    },
    series: [
      {
        type: "heatmap",
        data,
        label: {
          show: maxVal > 0 && sectors.length * months.length <= 120,
          formatter: (params: { value?: unknown }) => {
            const triple = params.value as [number, number, number] | undefined;
            const n = triple?.[2] ?? 0;
            return n > 0 ? String(n) : "";
          },
        },
        emphasis: {
          itemStyle: { shadowBlur: 6, shadowColor: "rgba(0, 0, 0, 0.25)" },
        },
      },
    ],
    tooltip: {
      position: "top",
      formatter: (params: { value?: unknown }) => {
        const triple = params.value as [number, number, number] | undefined;
        if (!triple) return "";
        const [xi, yi, value] = triple;
        return `${sectors[yi]} · ${months[xi]}: ${value}`;
      },
    },
    chartHeight: height,
  };
}
