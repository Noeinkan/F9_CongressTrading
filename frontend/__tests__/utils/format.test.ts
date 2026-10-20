import { describe, expect, it } from "vitest";

import { formatCompact, formatCurrency, formatMonthTick } from "@/utils/format";

describe("formatCurrency", () => {
  it("uses K, M and B tiers without trailing zeros", () => {
    expect(formatCurrency(1_500)).toBe("$1.5K");
    expect(formatCurrency(2_000_000)).toBe("$2M");
    expect(formatCurrency(1_250_000)).toBe("$1.3M");
    expect(formatCurrency(3_400_000_000)).toBe("$3.4B");
    expect(formatCurrency(-50_000)).toBe("-$50K");
    expect(formatCurrency(750)).toBe("$750");
  });

  it("keeps the dash for empty, zero and non-numeric values", () => {
    expect(formatCurrency(null)).toBe("—");
    expect(formatCurrency(0)).toBe("—");
    expect(formatCurrency("abc")).toBe("—");
  });
});

describe("formatCompact", () => {
  it("shortens counts and rounds small decimals", () => {
    expect(formatCompact(42)).toBe("42");
    expect(formatCompact(1_234)).toBe("1.2K");
    expect(formatCompact(3.4567)).toBe("3.5");
    expect(formatCompact(-2_000_000)).toBe("-2M");
    expect(formatCompact(undefined)).toBe("—");
  });
});

describe("formatMonthTick", () => {
  it("names the month", () => {
    expect(formatMonthTick("2026-05")).toBe("May 2026");
    expect(formatMonthTick("2023-12")).toBe("Dec 2023");
  });

  it("passes anything else through", () => {
    expect(formatMonthTick("2026-05-14")).toBe("2026-05-14");
    expect(formatMonthTick("Q1")).toBe("Q1");
    expect(formatMonthTick(null)).toBe("");
  });
});
