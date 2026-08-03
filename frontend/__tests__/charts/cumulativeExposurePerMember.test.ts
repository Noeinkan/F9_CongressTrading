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
    const band = series.find((s) => s.name === "Alice · band");
    const bandBase = series.find((s) => s.name === "Alice · band-base");
    const median = series.find((s) => s.name === "Alice");
    expect(bandBase).toBeTruthy();
    expect(band).toBeTruthy();
    expect(band!.stack).toBe(bandBase!.stack);
    expect(band!.step).toBe("end");
    expect(band!.areaStyle).toBeTruthy();
    expect(median!.type).toBe("line");
    expect(median!.step).toBe("end");
    expect(median!.z).toBeGreaterThan(band!.z as number);
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
    const yAxes = option!.yAxis as Array<Record<string, unknown>>;
    expect(yAxes[0]!.min as number).toBeLessThanOrEqual(-50_000);
    expect(yAxes[0]!.max as number).toBeGreaterThanOrEqual(50_000);
  });
});
