import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { RefreshControl } from "@/components/RefreshControl";

const useRefreshStatus = vi.fn();
const useStartRefresh = vi.fn();
const useCancelRefresh = vi.fn();

vi.mock("@/api/refresh", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/refresh")>();
  return {
    ...actual,
    useRefreshStatus: (...args: unknown[]) => useRefreshStatus(...args),
    useStartRefresh: (...args: unknown[]) => useStartRefresh(...args),
    useCancelRefresh: (...args: unknown[]) => useCancelRefresh(...args),
    readRefreshExpanded: () => false,
    writeRefreshExpanded: vi.fn(),
  };
});

vi.mock("@/hooks/useMediaQuery", async () => {
  const actual =
    await vi.importActual<typeof import("@/hooks/useMediaQuery")>("@/hooks/useMediaQuery");
  return { ...actual, useIsMobile: () => false };
});

const RUNNING = {
  status: "running",
  progress: 42,
  current_step: "ingest-house",
  phase_label: "Parsing House PTR PDFs",
  phase_index: 1,
  phase_total: 5,
  sub_progress: 30,
  sub_done: 3,
  sub_total: 10,
  sub_unit: "PDFs",
  eta_seconds: 90,
  started_at: "2026-06-08T21:00:00+00:00",
  log_lines: ["Scarico 2024 da https://example.com", "Trovati 120 PDF PTR"],
};

function renderControl() {
  return render(
    <MantineProvider>
      <RefreshControl />
    </MantineProvider>,
  );
}

describe("RefreshControl", () => {
  beforeEach(() => {
    useRefreshStatus.mockReturnValue({
      data: { status: "idle", progress: 0, current_step: "" },
    });
    useStartRefresh.mockReturnValue({ mutate: vi.fn(), isPending: false });
    useCancelRefresh.mockReturnValue({ mutate: vi.fn(), isPending: false });
  });

  it("shows the refresh button and no status while idle", () => {
    renderControl();
    expect(screen.getByTestId("sidebar-refresh")).toHaveTextContent("Refresh data");
    expect(screen.queryByTestId("topbar-refresh-status")).not.toBeInTheDocument();
  });

  it("clicking refresh triggers start mutation with no arguments", async () => {
    const user = userEvent.setup();
    const mutate = vi.fn();
    useStartRefresh.mockReturnValue({ mutate, isPending: false });
    renderControl();
    await user.click(screen.getByTestId("sidebar-refresh"));
    expect(mutate).toHaveBeenCalledTimes(1);
    expect(mutate).toHaveBeenCalledWith();
  });

  it("shows progress in the button and the phase as status while running", () => {
    useRefreshStatus.mockReturnValue({ data: RUNNING });
    renderControl();
    expect(screen.getByTestId("sidebar-refresh")).toHaveTextContent("Refreshing… 42%");
    expect(screen.getByTestId("sidebar-refresh")).toBeDisabled();
    expect(screen.getByTestId("topbar-refresh-status")).toHaveTextContent(
      "Parsing House PTR PDFs",
    );
  });

  it("status opens the popover with stepper, log, progress and cancel", async () => {
    const user = userEvent.setup();
    useRefreshStatus.mockReturnValue({ data: RUNNING });
    renderControl();

    expect(screen.queryByTestId("sidebar-refresh-popover")).not.toBeInTheDocument();
    await user.click(screen.getByTestId("sidebar-refresh-expand"));
    expect(await screen.findByTestId("sidebar-refresh-popover")).toBeInTheDocument();
    expect(screen.getByTestId("sidebar-refresh-phase-1")).toBeInTheDocument();
    expect(screen.getByTestId("sidebar-refresh-progress")).toBeInTheDocument();
    expect(screen.getByTestId("sidebar-refresh-cancel")).toBeInTheDocument();
    expect(screen.getByText("Scarico 2024 da https://example.com")).toBeInTheDocument();
    expect(screen.getByTestId("sidebar-refresh-eta")).toHaveTextContent("ETA");
  });

  it("shows an Updated status and the completion note after success", async () => {
    const user = userEvent.setup();
    useRefreshStatus.mockReturnValue({
      data: {
        status: "succeeded",
        progress: 100,
        current_step: "done",
        started_at: "2026-06-08T21:00:00+00:00",
        finished_at: "2026-06-08T21:05:00+00:00",
        result: { scope: "ingest-all" },
      },
    });
    renderControl();
    expect(screen.getByTestId("topbar-refresh-status")).toHaveTextContent(/^Updated/);
    await user.click(screen.getByTestId("sidebar-refresh-expand"));
    expect(await screen.findByTestId("sidebar-refresh-success")).toHaveTextContent("Refresh completed");
  });

  it("offers a retry and shows the error after a failure", () => {
    useRefreshStatus.mockReturnValue({
      data: {
        status: "failed",
        progress: 30,
        started_at: "2026-06-08T21:00:00+00:00",
        result: { error: "Clerk returned 503" },
      },
    });
    renderControl();
    expect(screen.getByTestId("sidebar-refresh")).toHaveTextContent("Retry refresh");
    expect(screen.getByTestId("topbar-refresh-status")).toHaveTextContent("Clerk returned 503");
  });
});
