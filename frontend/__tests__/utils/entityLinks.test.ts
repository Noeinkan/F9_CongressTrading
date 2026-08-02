import { describe, expect, it } from "vitest";

import {
  hrefFromChartClick,
  memberHref,
  splitMemberNames,
  tickerHref,
} from "@/utils/entityLinks";

describe("entityLinks", () => {
  it("builds member and ticker hrefs", () => {
    expect(memberHref("Hon. Nancy Pelosi")).toBe(
      `/members?member=${encodeURIComponent("Hon. Nancy Pelosi")}`,
    );
    expect(memberHref("Alice", { view: "committee_relevance" })).toBe(
      `/members?member=Alice&view=committee_relevance`,
    );
    expect(tickerHref("nvda")).toBe("/tickers?ticker=nvda");
    expect(tickerHref("NVDA", "msft")).toBe("/tickers?ticker=NVDA&ticker_override=MSFT");
  });

  it("splits comma-joined member name blobs", () => {
    expect(splitMemberNames("Alice, Bob, Carol")).toEqual(["Alice", "Bob", "Carol"]);
    expect(splitMemberNames("  Alice ,  Bob  ")).toEqual(["Alice", "Bob"]);
    expect(splitMemberNames("")).toEqual([]);
  });

  it("resolves chart clicks to hrefs", () => {
    expect(hrefFromChartClick({ componentType: "series", name: "MSFT" }, "ticker")).toBe(
      "/tickers?ticker=MSFT",
    );
    expect(
      hrefFromChartClick(
        { componentType: "series", value: ["2024-01-01", "Hon. Alice", 1000] },
        "member",
      ),
    ).toBe(`/members?member=${encodeURIComponent("Hon. Alice")}`);
    expect(
      hrefFromChartClick(
        { componentType: "yAxis", value: "AMZN" },
        "ticker",
      ),
    ).toBe("/tickers?ticker=AMZN");
    expect(
      hrefFromChartClick(
        { componentType: "series", seriesName: "Hon. Bob · trades", value: [1, 2] },
        "member",
      ),
    ).toBe(`/members?member=${encodeURIComponent("Hon. Bob")}`);
    expect(hrefFromChartClick({ componentType: "series" }, "member")).toBeNull();
  });
});
