import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiFetch, onDemoRefusal } from "@/api/client";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("apiFetch", () => {
  it("sends credentials: include", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({ status: "ok" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await apiFetch("/api/health");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/health",
      expect.objectContaining({ credentials: "include" }),
    );
  });

  it("parses JSON on success", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({ user: "dashboard" }),
      }),
    );

    const result = await apiFetch<{ user: string }>("/api/me");
    expect(result.user).toBe("dashboard");
  });

  it("throws ApiError on non-2xx with status and body", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({ detail: "Not authenticated" }),
      }),
    );

    await expect(apiFetch("/api/me")).rejects.toMatchObject({
      name: "ApiError",
      status: 401,
      body: { detail: "Not authenticated" },
    } satisfies Partial<ApiError>);
  });

  it("broadcasts a DEMO_* refusal to onDemoRefusal listeners, then still throws", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 403,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({ code: "DEMO_LOCKED", feature: "csv_export", detail: "Nope." }),
      }),
    );

    const listener = vi.fn();
    const unsubscribe = onDemoRefusal(listener);
    try {
      await expect(apiFetch("/api/home/net_trade.csv")).rejects.toMatchObject({
        name: "ApiError",
        status: 403,
      });
      expect(listener).toHaveBeenCalledWith({
        code: "DEMO_LOCKED",
        feature: "csv_export",
        detail: "Nope.",
      });
    } finally {
      unsubscribe();
    }
  });

  it("does not broadcast an ordinary error body without a DEMO_* code", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({ detail: "Internal error" }),
      }),
    );

    const listener = vi.fn();
    const unsubscribe = onDemoRefusal(listener);
    try {
      await expect(apiFetch("/api/health")).rejects.toBeInstanceOf(ApiError);
      expect(listener).not.toHaveBeenCalled();
    } finally {
      unsubscribe();
    }
  });
});
