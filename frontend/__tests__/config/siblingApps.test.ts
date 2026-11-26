import { afterEach, describe, expect, it, vi } from "vitest";

import { configuredSiblings, siblingBaseUrl, siblingUrl } from "@/config/siblingApps";

describe("sibling app links", () => {
  afterEach(() => vi.unstubAllEnvs());

  it("points at the production sites by default", () => {
    vi.stubEnv("VITE_SEARCHFORALPHA_URL", undefined as unknown as string);
    vi.stubEnv("VITE_13F_URL", undefined as unknown as string);
    expect(siblingUrl("sfa", "nvda")).toBe("https://alpha.noeinsolutions.com/ticker/NVDA?from=congress");
    expect(siblingUrl("13f", "NVDA")).toBe(
      "https://13f.noeinsolutions.com/holdings-search?q=NVDA&from=congress",
    );
    expect(configuredSiblings()).toEqual(["sfa", "13f"]);
  });

  it("never links to a demo, even when a variable names one", () => {
    vi.stubEnv("VITE_13F_URL", "https://13f.demos.noeinsolutions.com");
    expect(siblingBaseUrl("13f")).toBeNull();
    expect(configuredSiblings()).not.toContain("13f");
  });

  it("hides an app whose variable is set empty", () => {
    vi.stubEnv("VITE_SEARCHFORALPHA_URL", "");
    expect(siblingUrl("sfa", "NVDA")).toBeNull();
  });
});
