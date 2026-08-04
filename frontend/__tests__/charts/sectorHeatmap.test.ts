import { describe, expect, it } from "vitest";

import { buildSectorHeatmapOption } from "@/charts/sectorHeatmap";

describe("buildSectorHeatmapOption", () => {
  it("returns null for empty input", () => {
    expect(buildSectorHeatmapOption([])).toBeNull();
  });

  it("builds month × sector heatmap data", () => {
    const option = buildSectorHeatmapOption([
      { month: "2024-06-01", sector: "Energy", transactions: 2 },
      { month: "2024-06-01", sector: "Information Technology", transactions: 5 },
      { month: "2024-07-01", sector: "Energy", transactions: 1 },
    ]);
    expect(option).not.toBeNull();
    expect(option?.xAxis).toMatchObject({
      type: "category",
      data: ["2024-06", "2024-07"],
    });
    const yAxis = option?.yAxis as { data: string[] };
    expect(yAxis.data[0]).toBe("Information Technology");
    expect(yAxis.data).toContain("Energy");
    const series = option?.series as Array<{ data: [number, number, number][] }>;
    expect(series[0]?.data.length).toBe(4);
    const itJune = series[0]?.data.find(([x, y]) => x === 0 && y === 0);
    expect(itJune?.[2]).toBe(5);
  });
});
