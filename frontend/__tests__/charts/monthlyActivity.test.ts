import { describe, expect, it } from "vitest";

import {
  buildMonthlyActivityOption,
  incompleteMonthKeys,
  isMonthLikelyIncomplete,
  monthKey,
  type MonthlyActivityRow,
} from "@/charts/monthlyActivity";

function row(partial: Partial<MonthlyActivityRow> & Pick<MonthlyActivityRow, "month">): MonthlyActivityRow {
  return {
    transactions: 0,
    buy: 0,
    sell: 0,
    other: 0,
    amount_low: 0,
    amount_high: 0,
    ...partial,
  };
}

describe("monthKey", () => {
  it("keeps YYYY-MM from ISO dates", () => {
    expect(monthKey("2026-04-01")).toBe("2026-04");
    expect(monthKey("2026-04")).toBe("2026-04");
  });
});

describe("isMonthLikelyIncomplete", () => {
  it("marks the current and recent months inside the lag window", () => {
    const now = new Date(2026, 7, 2); // 2 Aug 2026
    expect(isMonthLikelyIncomplete("2026-08", now)).toBe(true);
    expect(isMonthLikelyIncomplete("2026-07", now)).toBe(true);
    expect(isMonthLikelyIncomplete("2026-06", now)).toBe(true);
    expect(isMonthLikelyIncomplete("2026-05", now)).toBe(false);
  });
});

describe("incompleteMonthKeys", () => {
  it("returns only months still inside the lag window", () => {
    const now = new Date(2026, 7, 2);
    expect(
      incompleteMonthKeys(["2026-04", "2026-05", "2026-06", "2026-07"], now),
    ).toEqual(["2026-06", "2026-07"]);
  });
});

describe("buildMonthlyActivityOption", () => {
  it("builds stacked buy/sell bars and a dollar line", () => {
    const option = buildMonthlyActivityOption(
      [
        row({
          month: "2024-01-01",
          transactions: 3,
          buy: 1,
          sell: 1,
          other: 1,
          amount_low: 1000,
          amount_high: 15000,
        }),
        row({
          month: "2024-02-01",
          transactions: 2,
          buy: 2,
          sell: 0,
          other: 0,
          amount_low: 5000,
          amount_high: 25000,
        }),
      ],
      new Date(2024, 5, 15),
    );

    expect(option.legend).toBeTruthy();
    expect(Array.isArray(option.yAxis)).toBe(true);
    const series = option.series as Array<{ name: string; type: string; stack?: string; data: number[] }>;
    expect(series.map((s) => s.name)).toEqual(["Buy", "Sell", "Other", "Disclosed $ high"]);
    expect(series[0]?.stack).toBe("side");
    expect(series[0]?.data).toEqual([1, 2]);
    expect(series[1]?.data).toEqual([1, 0]);
    expect(series[3]?.type).toBe("line");
    expect(series[3]?.data).toEqual([15000, 25000]);
  });

  it("shades incomplete months with a markArea", () => {
    const option = buildMonthlyActivityOption(
      [
        row({ month: "2026-05-01", transactions: 10, buy: 6, sell: 4, amount_high: 1000 }),
        row({ month: "2026-06-01", transactions: 8, buy: 5, sell: 3, amount_high: 800 }),
        row({ month: "2026-07-01", transactions: 2, buy: 1, sell: 1, amount_high: 200 }),
      ],
      new Date(2026, 7, 2),
    );
    const series = option.series as Array<{ markArea?: { data: unknown[] } }>;
    expect(series[0]?.markArea?.data).toEqual([[{ xAxis: "2026-06" }, { xAxis: "2026-07" }]]);
  });

  it("derives other from total when buy/sell are omitted", () => {
    const option = buildMonthlyActivityOption(
      [{ month: "2024-01-01", transactions: 5, amount_low: 0, amount_high: 100 }],
      new Date(2020, 0, 1),
    );
    const series = option.series as Array<{ name: string; data: number[] }>;
    const other = series.find((s) => s.name === "Other");
    expect(other?.data).toEqual([5]);
    expect(series.find((s) => s.name === "Buy")?.data).toEqual([0]);
    expect(series.find((s) => s.name === "Sell")?.data).toEqual([0]);
  });
});
