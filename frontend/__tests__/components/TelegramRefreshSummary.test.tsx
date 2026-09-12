import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { refreshStatusQueryKey, type RefreshStatusResponse } from "@/api/refresh";
import {
  formatSentAt,
  TelegramRefreshSummary,
  telegramSummary,
} from "@/components/TelegramRefreshSummary";

const apiFetch = vi.fn();

vi.mock("@/api/client", () => ({
  apiFetch: (...args: unknown[]) => apiFetch(...args),
}));

const SENT_AT = "2026-09-12T12:02:00Z";

const heldBack = {
  exports: "wrote congress_trades.csv",
  alerts: "quiet - 3 new row(s), none notable",
  digest: `skipped - digest already sent 0.4h ago (${SENT_AT}); not repeated within 12h`,
  digest_sent_at: SENT_AT,
};

function Harness() {
  // Reads the cached refresh result the way the sidebar does, so a patched
  // cache after "Send digest again" re-renders the line.
  const { data } = useQuery<RefreshStatusResponse>({
    queryKey: refreshStatusQueryKey,
    queryFn: () => Promise.reject(new Error("not fetched in tests")),
    enabled: false,
  });
  const summary = telegramSummary(data?.result.post_ingest);
  return summary ? <TelegramRefreshSummary summary={summary} /> : null;
}

function renderWithCachedRun(postIngest: Record<string, string>) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  client.setQueryData(refreshStatusQueryKey, {
    status: "succeeded",
    result: { post_ingest: postIngest },
  } as unknown as RefreshStatusResponse);
  return render(
    <QueryClientProvider client={client}>
      <MantineProvider>
        <Harness />
      </MantineProvider>
    </QueryClientProvider>,
  );
}

describe("telegramSummary", () => {
  it("recognises a digest held back by the cooldown", () => {
    const summary = telegramSummary(heldBack);
    expect(summary?.digestHeldBack).toBe(true);
    expect(summary?.text).toBe("Telegram — alerts: quiet · digest: not repeated");
    expect(summary?.digestSentAt).toBe(SENT_AT);
  });

  it("does not offer a resend when Telegram is simply not configured", () => {
    expect(
      telegramSummary({ alerts: "skipped - not configured", digest: "skipped - not configured" })
        ?.digestHeldBack,
    ).toBe(false);
  });

  it("flags any failed step", () => {
    expect(
      telegramSummary({ exports: "failed - PermissionError: locked", alerts: "sent - 1", digest: "sent - ok" })
        ?.failed,
    ).toBe(true);
  });

  it("is null for runs that never reached the Telegram phase", () => {
    expect(telegramSummary(undefined)).toBeNull();
  });
});

describe("formatSentAt", () => {
  it("says today for a send earlier the same day", () => {
    const sent = new Date(2026, 8, 12, 9, 5);
    expect(formatSentAt(sent.toISOString(), new Date(2026, 8, 12, 18, 0))).toMatch(/^today at /);
  });

  it("names the day for an older send", () => {
    const sent = new Date(2026, 8, 11, 9, 5);
    expect(formatSentAt(sent.toISOString(), new Date(2026, 8, 12, 18, 0))).toMatch(/^on .+ at /);
  });
});

describe("TelegramRefreshSummary", () => {
  beforeEach(() => {
    apiFetch.mockReset();
  });

  it("explains the skipped digest and resends it once on request", async () => {
    apiFetch.mockResolvedValue({ status: "sent", message: "weekly digest - delivered", sent_at: SENT_AT });
    renderWithCachedRun(heldBack);

    expect(screen.getByTestId("refresh-digest-held-back")).toHaveTextContent(
      /already went out .* so this refresh did not send another/,
    );

    await userEvent.click(screen.getByTestId("refresh-digest-resend"));

    expect(apiFetch).toHaveBeenCalledWith("/api/admin/send-digest", { method: "POST" });
    // The button goes away as soon as the digest is out: no second accidental send.
    await waitFor(() =>
      expect(screen.queryByTestId("refresh-digest-resend")).not.toBeInTheDocument(),
    );
    expect(screen.getByText(/digest: sent /)).toBeInTheDocument();
    expect(apiFetch).toHaveBeenCalledTimes(1);
  });

  it("keeps the button and shows why when the resend fails", async () => {
    apiFetch.mockResolvedValue({ status: "failed", message: "digest NOT delivered: 401", sent_at: "" });
    renderWithCachedRun(heldBack);

    await userEvent.click(screen.getByTestId("refresh-digest-resend"));

    expect(await screen.findByTestId("refresh-digest-resend-error")).toHaveTextContent(
      "Digest not sent: digest NOT delivered: 401",
    );
    expect(screen.getByTestId("refresh-digest-resend")).toBeInTheDocument();
  });
});
