import { describe, expect, it } from "vitest";

import {
  DISCLOSED_RANGE_BUCKETS,
  classifyAmountRange,
  rangeOpacity,
} from "@/utils/transactions";

describe("classifyAmountRange", () => {
  it("maps a $1K-$15K row to the 1k-15k bucket", () => {
    expect(
      classifyAmountRange({ amount_low: 1_000, amount_high: 15_000, amount_range_raw: "$1K – $15K" }),
    ).toBe("1k-15k");
  });

  it("maps a $750K row to the 500k-1m bucket", () => {
    expect(
      classifyAmountRange({ amount_low: 500_001, amount_high: 750_000, amount_range_raw: "$500K – $1M" }),
    ).toBe("500k-1m");
  });

  it("maps a $60M row to the open-ended over-50m bucket", () => {
    expect(
      classifyAmountRange({ amount_low: 50_000_001, amount_high: 60_000_000, amount_range_raw: "Over $50M" }),
    ).toBe("over-50m");
  });

  it("falls back to amount_range_raw when amount_low/high are missing", () => {
    expect(
      classifyAmountRange({ amount_low: null, amount_high: null, amount_range_raw: "$15K – $50K" }),
    ).toBe("15k-50k");
  });

  it("returns null when no numeric value can be derived", () => {
    expect(
      classifyAmountRange({ amount_low: null, amount_high: null, amount_range_raw: "" }),
    ).toBeNull();
  });

  it("matches every bucket in the canonical PTR band list", () => {
    const samples: Array<[number, string]> = [
      [5_000, "1k-15k"],
      [25_000, "15k-50k"],
      [75_000, "50k-100k"],
      [175_000, "100k-250k"],
      [400_000, "250k-500k"],
      [750_000, "500k-1m"],
      [3_000_000, "1m-5m"],
      [10_000_000, "5m-25m"],
      [40_000_000, "25m-50m"],
      [75_000_000, "over-50m"],
    ];
    for (const [value, key] of samples) {
      expect(classifyAmountRange({ amount_low: value, amount_high: value })).toBe(key);
    }
    // Sanity: every key we just sampled is in the published bucket list.
    for (const key of samples.map(([, k]) => k)) {
      expect(DISCLOSED_RANGE_BUCKETS.some((b) => b.key === key)).toBe(true);
    }
  });

  it("leaves rangeOpacity unchanged for the existing call signature", () => {
    expect(rangeOpacity("$1K – $15K")).toBeLessThan(rangeOpacity("$1M – $5M"));
  });
});