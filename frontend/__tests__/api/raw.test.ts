import { describe, expect, it } from "vitest";

import { rawExportCsvUrl } from "@/api/raw";

describe("raw API helpers", () => {
  it("rawExportCsvUrl includes sort and pagination params", () => {
    const url = rawExportCsvUrl({
      lookback: 1,
      sort: "transaction_date",
      order: "desc",
      page: 2,
      page_size: 50,
    });
    expect(url).toContain("/api/raw/export.csv");
    expect(url).toContain("lookback=1");
    expect(url).toContain("sort=transaction_date");
    expect(url).toContain("order=desc");
    expect(url).toContain("page=2");
    expect(url).toContain("page_size=50");
  });

  it("rawExportCsvUrl encodes all-time lookback", () => {
    expect(rawExportCsvUrl({ lookback: null })).toContain("lookback=0");
  });
});
