import { describe, expect, it } from "vitest";

import type { TickerCumulativeExposureRow } from "@/api/types";
import { buildCumulativeExposurePerMemberOption } from "@/charts/cumulativeExposurePerMember";

function row(
  partial: Partial<TickerCumulativeExposureRow> &
    Pick<TickerCumulativeExposureRow, "member" | "transaction_date" | "cumulative_net">,
): TickerCumulativeExposureRow {
  return {
    cumulative_low: partial.cumulative_low ?? partial.cumulative_net,
    cumulative_high: partial.cumulative_high ?? partial.cumulative_net,
    cumulative_label: "$0 net",
    txn_type_label: "Buy",
    amount_range_raw: "",
    ...partial,
  };
}

describe("buildCumulativeExposurePerMemberOption", () => {
  it("returns null for empty input", () => {
    expect(buildCumulativeExposurePerMemberOption([], [])).toBeNull();
  });

  it("draws a stepped band between cumulative_low and cumulative_high", () => {
    const rows = [
      row({
        member: "Alice",
        transaction_date: "2024-01-10",
        cumulative_net: 8_000,
        cumulative_low: 1_000,
        cumulative_high: 15_000,
        cumulative_label: "~$8.0K (range $1.0K – $15.0K)",
        txn_type_label: "Buy",
      }),
      row({
        member: "Alice",
        transaction_date: "2024-02-10",
        cumulative_net: 0,
        cumulative_low: -14_000,
        cumulative_high: 14_000,
        cumulative_label: "~$0 (range -$14.0K – $14.0K)",
        txn_type_label: "Sell",
      }),
    ];
    const option = buildCumulativeExposurePerMemberOption(rows, ["Alice"]);
    expect(option).not.toBeNull();
    const series = option!.series as Array<Record<string, unknown>>;
    // Band + median share the member name so legend toggles hide both.
    const aliceSeries = series.filter((s) => s.name === "Alice");
    const band = aliceSeries.find(
      (s) => s.areaStyle && (s.areaStyle as { color?: string }).color,
    );
    const bandBase = aliceSeries.find(
      (s) => s.stack && s.areaStyle && !(s.areaStyle as { color?: string }).color,
    );
    const median = aliceSeries.find((s) => s.type === "line" && s.endLabel);
    expect(bandBase).toBeTruthy();
    expect(band).toBeTruthy();
    expect(band!.stack).toBe(bandBase!.stack);
    expect(band!.step).toBe("end");
    expect(band!.areaStyle).toBeTruthy();
    expect(median!.type).toBe("line");
    expect(median!.step).toBe("end");
    expect(median!.z).toBeGreaterThan(band!.z as number);
  });

  it("uses a single shared canvas (one grid / one y-axis)", () => {
    const rows = [
      row({
        member: "Alice",
        transaction_date: "2024-01-10",
        cumulative_net: 5_000,
        txn_type_label: "Buy",
      }),
      row({
        member: "Bob",
        transaction_date: "2024-01-15",
        cumulative_net: -3_000,
        txn_type_label: "Sell",
      }),
    ];
    const option = buildCumulativeExposurePerMemberOption(rows, ["Alice", "Bob"]);
    expect(option).not.toBeNull();
    expect(Array.isArray(option!.grid)).toBe(false);
    expect(Array.isArray(option!.yAxis)).toBe(false);
    expect(Array.isArray(option!.xAxis)).toBe(false);
    const legend = option!.legend as { data: Array<{ name: string }>; selectedMode: boolean };
    expect(legend.selectedMode).toBe(true);
    expect(legend.data.map((d) => d.name)).toEqual(["Alice", "Bob"]);
  });

  it("extends shared y-domain to floor/ceiling extremes", () => {
    const rows = [
      row({
        member: "Alice",
        transaction_date: "2024-01-10",
        cumulative_net: 0,
        cumulative_low: -50_000,
        cumulative_high: 50_000,
        txn_type_label: "Buy",
      }),
    ];
    const option = buildCumulativeExposurePerMemberOption(rows, ["Alice"]);
    const yAxis = option!.yAxis as Record<string, unknown>;
    expect(yAxis.min as number).toBeLessThanOrEqual(-50_000);
    expect(yAxis.max as number).toBeGreaterThanOrEqual(50_000);
  });
});
