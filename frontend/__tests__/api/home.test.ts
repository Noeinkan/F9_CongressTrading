import { describe, expect, it } from "vitest";

import { netTradeCsvUrl } from "@/api/home";
import { buildPeriodSearch } from "@/api/params";

describe("home API helpers", () => {
  it("buildPeriodSearch encodes lookback and quarters", () => {
    expect(buildPeriodSearch({ lookback: 2, quarters: "1,2" })).toBe("?lookback=2&quarters=1%2C2");
  });

  it("buildPeriodSearch encodes all-time as lookback=0", () => {
    expect(buildPeriodSearch({ lookback: null })).toBe("?lookback=0");
  });

  it("netTradeCsvUrl includes period params", () => {
    expect(netTradeCsvUrl({ lookback: 1, quarters: "1,2,3,4" })).toBe(
      "/api/home/net_trade.csv?lookback=1&quarters=1%2C2%2C3%2C4",
    );
  });
});
