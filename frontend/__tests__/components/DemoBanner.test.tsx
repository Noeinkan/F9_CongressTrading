import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DemoBanner } from "@/components/DemoBanner";

const navigateMock = vi.fn();
vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => navigateMock };
});

const useDemoStatusMock = vi.fn();
const signOutMutateAsyncMock = vi.fn();
vi.mock("@/api/demo", () => ({
  demoQueryKey: ["demo", "status"],
  useDemoStatus: () => useDemoStatusMock(),
  useDemoSignOut: () => ({ mutateAsync: signOutMutateAsyncMock }),
}));

const NOW = new Date("2026-09-16T10:00:00Z");

function renderBanner() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MantineProvider>
        <MemoryRouter>
          <DemoBanner />
        </MemoryRouter>
      </MantineProvider>
    </QueryClientProvider>,
  );
}

describe("DemoBanner", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    useDemoStatusMock.mockReset();
    signOutMutateAsyncMock.mockReset();
    signOutMutateAsyncMock.mockResolvedValue({ ok: true });
    navigateMock.mockReset();
    vi.useFakeTimers();
    vi.setSystemTime(NOW);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders nothing on a normal deployment", () => {
    useDemoStatusMock.mockReturnValue({ data: { enabled: false } });
    renderBanner();
    expect(screen.queryByTestId("demo-banner")).not.toBeInTheDocument();
  });

  it("renders nothing while the status is still loading", () => {
    useDemoStatusMock.mockReturnValue({ data: undefined });
    renderBanner();
    expect(screen.queryByTestId("demo-banner")).not.toBeInTheDocument();
  });

  it("states the limits and the snapshot date when the demo is live", () => {
    useDemoStatusMock.mockReturnValue({
      data: {
        enabled: true,
        readOnly: true,
        notice: "You are in the public demo.",
        snapshotLabel: "Snapshot: 12 September 2026",
        sourceUrl: "https://noeinsolutions.com/builds.html",
      },
    });
    renderBanner();
    expect(screen.getByTestId("demo-banner")).toBeInTheDocument();
    expect(screen.getByText("You are in the public demo.")).toBeInTheDocument();
    expect(screen.getByTestId("demo-banner-snapshot")).toHaveTextContent(
      "Snapshot: 12 September 2026",
    );
    expect(screen.getByText(/does not refresh/i)).toBeInTheDocument();
  });

  it("stays dismissed for the rest of the tab session", () => {
    useDemoStatusMock.mockReturnValue({
      data: { enabled: true, notice: "Demo.", snapshotLabel: "Snapshot: 12 September 2026" },
    });
    const { unmount } = renderBanner();
    fireEvent.click(screen.getByLabelText(/dismiss the demo notice/i));
    expect(screen.queryByTestId("demo-banner")).not.toBeInTheDocument();

    unmount();
    renderBanner();
    expect(screen.queryByTestId("demo-banner")).not.toBeInTheDocument();
  });

  it("hides the countdown entirely when the access gate is off", () => {
    useDemoStatusMock.mockReturnValue({
      data: {
        enabled: true,
        notice: "Demo.",
        access: {
          gate: false,
          status: "active",
          expiresAt: "2026-09-16T10:10:00Z",
          serverNow: NOW.toISOString(),
        },
      },
    });
    renderBanner();
    expect(screen.queryByTestId("demo-countdown-bar")).not.toBeInTheDocument();
  });

  it("renders a countdown computed from expiresAt and serverNow", () => {
    useDemoStatusMock.mockReturnValue({
      data: {
        enabled: true,
        notice: "Demo.",
        access: {
          gate: true,
          status: "active",
          address: "person@example.com",
          expiresAt: "2026-09-16T10:10:00Z",
          serverNow: NOW.toISOString(),
        },
      },
    });
    renderBanner();
    expect(screen.getByTestId("demo-countdown")).toHaveTextContent("10:00 left");
    expect(screen.getByTestId("demo-banner-identity")).toHaveTextContent(
      "Signed in as person@example.com",
    );
  });

  it("turns red once under 5 minutes remain", () => {
    useDemoStatusMock.mockReturnValue({
      data: {
        enabled: true,
        notice: "Demo.",
        access: {
          gate: true,
          status: "active",
          expiresAt: "2026-09-16T10:04:30Z",
          serverNow: NOW.toISOString(),
        },
      },
    });
    renderBanner();
    const badge = screen.getByTestId("demo-countdown");
    expect(badge).toHaveTextContent("4:30 left");
    expect(badge).toHaveAttribute("data-red-zone", "true");
  });

  it("keeps the countdown and sign-out visible after the notice is dismissed", () => {
    useDemoStatusMock.mockReturnValue({
      data: {
        enabled: true,
        notice: "Demo.",
        access: {
          gate: true,
          status: "active",
          address: "person@example.com",
          expiresAt: "2026-09-16T10:10:00Z",
          serverNow: NOW.toISOString(),
        },
      },
    });
    renderBanner();
    fireEvent.click(screen.getByLabelText(/dismiss the demo notice/i));
    expect(screen.queryByTestId("demo-banner")).not.toBeInTheDocument();
    expect(screen.getByTestId("demo-countdown")).toBeInTheDocument();
    expect(screen.getByTestId("demo-banner-identity")).toBeInTheDocument();
  });

  it("navigates to /access/ended once the countdown reaches zero", () => {
    useDemoStatusMock.mockReturnValue({
      data: {
        enabled: true,
        notice: "Demo.",
        access: {
          gate: true,
          status: "active",
          expiresAt: "2026-09-16T10:00:02Z",
          serverNow: NOW.toISOString(),
        },
      },
    });
    renderBanner();
    act(() => {
      vi.advanceTimersByTime(3000);
    });
    expect(navigateMock).toHaveBeenCalledWith("/access/ended");
  });

  it("signs out and returns to /access when Sign out is clicked", async () => {
    useDemoStatusMock.mockReturnValue({
      data: {
        enabled: true,
        notice: "Demo.",
        access: { gate: true, status: "active", address: "person@example.com" },
      },
    });
    renderBanner();
    await act(async () => {
      fireEvent.click(screen.getByTestId("demo-banner-signout"));
    });
    expect(signOutMutateAsyncMock).toHaveBeenCalled();
  });
});
