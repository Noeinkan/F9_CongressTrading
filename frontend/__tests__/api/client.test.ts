import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiFetch } from "@/api/client";

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
});
