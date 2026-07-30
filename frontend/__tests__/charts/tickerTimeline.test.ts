import { describe, expect, it } from "vitest";

import { amountToSymbolSize, buildTickerTimelineOption } from "@/charts/tickerTimeline";
import type { TickerTimelineRow } from "@/api/types";

function row(partial: Partial<TickerTimelineRow> & Pick<TickerTimelineRow, "member" | "transaction_date">): TickerTimelineRow {
  return {
    transaction_type: "P",
    txn_type_label: "Buy",
    amount_low: null,
    amount_high: null,
    ...partial,
  };
}

describe("amountToSymbolSize", () => {
  it("uses a default size when amount is missing", () => {
    expect(amountToSymbolSize(null)).toBe(11);
  });

  it("grows with disclosed high amount on a log scale", () => {
    const small = amountToSymbolSize(1_000);
    const large = amountToSymbolSize(1_000_000);
    expect(small).toBeLessThan(large);
    expect(small).toBeGreaterThanOrEqual(8);
    expect(large).toBeLessThanOrEqual(28);
  });
});

describe("buildTickerTimelineOption", () => {
  it("returns null for empty rows", () => {
    expect(buildTickerTimelineOption([])).toBeNull();
  });

  it("encodes amount_high as the third data value for symbol sizing", () => {
    const option = buildTickerTimelineOption([
      row({
        member: "Alice",
        transaction_date: "2024-03-01",
        amount_high: 15_000,
        txn_type_label: "Buy",
      }),
      row({
        member: "Bob",
        transaction_date: "2024-04-01",
        amount_high: 500_000,
        txn_type_label: "Sell",
        transaction_type: "S",
      }),
    ]);
    expect(option).not.toBeNull();
    const series = option!.series as Array<{ name: string; data: unknown[] }>;
    const buy = series.find((s) => s.name === "Buy");
    expect(buy?.data[0]).toEqual(["2024-03-01", "Alice", 15_000]);
  });
});
