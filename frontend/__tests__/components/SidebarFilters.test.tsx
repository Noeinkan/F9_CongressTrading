import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { FilterProvider, useFilters } from "@/components/FilterContext";
import { SidebarFilters } from "@/components/SidebarFilters";

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

function Probe() {
  const { lookback, quarters } = useFilters();
  return (
    <div>
      <span data-testid="probe-lookback">{lookback}</span>
      <span data-testid="probe-quarters">{quarters.join(",")}</span>
    </div>
  );
}

function renderSidebar(initial?: { lookback?: number; quarters?: ("1" | "2" | "3" | "4")[] }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MantineProvider>
        <MemoryRouter>
          <FilterProvider
            initialLookback={initial?.lookback}
            initialQuarters={initial?.quarters}
          >
            <SidebarFilters />
            <Probe />
          </FilterProvider>
        </MemoryRouter>
      </MantineProvider>
    </QueryClientProvider>,
  );
}

describe("SidebarFilters", () => {
  beforeEach(() => {
    const mutate = vi.fn();
    useRefreshStatus.mockReturnValue({
      data: { status: "idle", progress: 0, current_step: "" },
    });
    useStartRefresh.mockReturnValue({ mutate, isPending: false });
    useCancelRefresh.mockReturnValue({ mutate: vi.fn(), isPending: false });
  });

  it("renders the sidebar shell", () => {
    renderSidebar();
    expect(screen.getByTestId("sidebar-filters")).toBeInTheDocument();
    expect(screen.getByTestId("sidebar-lookback")).toBeInTheDocument();
    expect(screen.getByTestId("sidebar-quarters")).toBeInTheDocument();
    expect(screen.getByTestId("sidebar-reset")).toBeInTheDocument();
  });

  it("shows all four quarter buttons", () => {
    renderSidebar();
    const quarters = screen.getByTestId("sidebar-quarters");
    for (const q of ["1", "2", "3", "4"]) {
      expect(within(quarters).getByTestId(`sidebar-quarter-${q}`)).toBeInTheDocument();
    }
  });

  it("reset returns lookback and quarters to defaults", async () => {
    const user = userEvent.setup();
    renderSidebar({ lookback: 5, quarters: ["1"] });
    expect(screen.getByTestId("probe-lookback")).toHaveTextContent("5");
    expect(screen.getByTestId("probe-quarters")).toHaveTextContent("1");

    await user.click(screen.getByTestId("sidebar-reset"));
    expect(screen.getByTestId("probe-lookback")).toHaveTextContent("1");
    expect(screen.getByTestId("probe-quarters")).toHaveTextContent("1,2,3,4");
  });

  it("toggling a quarter updates the context", async () => {
    const user = userEvent.setup();
    renderSidebar({ quarters: ["1", "2", "3", "4"] });
    await user.click(screen.getByTestId("sidebar-quarter-2"));
    expect(screen.getByTestId("probe-quarters")).toHaveTextContent("1,3,4");
  });

  it("toggling the last remaining quarter is a no-op", async () => {
    const user = userEvent.setup();
    renderSidebar({ quarters: ["1"] });
    await user.click(screen.getByTestId("sidebar-quarter-1"));
    expect(screen.getByTestId("probe-quarters")).toHaveTextContent("1");
  });

  it("renders refresh data admin control", () => {
    renderSidebar();
    expect(screen.getByTestId("sidebar-admin")).toBeInTheDocument();
    expect(screen.getByTestId("sidebar-refresh")).toHaveTextContent("Refresh data");
  });

  it("clicking refresh triggers start mutation with no arguments", async () => {
    const user = userEvent.setup();
    const mutate = vi.fn();
    useStartRefresh.mockReturnValue({ mutate, isPending: false });
    renderSidebar();
    await user.click(screen.getByTestId("sidebar-refresh"));
    expect(mutate).toHaveBeenCalledTimes(1);
    expect(mutate).toHaveBeenCalledWith();
  });

  it("does not render the legacy refresh option checkboxes", () => {
    renderSidebar();
    expect(screen.queryByTestId("sidebar-refresh-overwrite")).not.toBeInTheDocument();
    expect(screen.queryByTestId("sidebar-refresh-force-extract")).not.toBeInTheDocument();
    expect(screen.queryByTestId("sidebar-refresh-skip-senate")).not.toBeInTheDocument();
  });

  it("shows progress and cancel while refresh is running", () => {
    useRefreshStatus.mockReturnValue({
      data: {
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
      },
    });
    useStartRefresh.mockReturnValue({ mutate: vi.fn(), isPending: false });
    renderSidebar();
    expect(screen.getByTestId("sidebar-refresh-progress")).toBeInTheDocument();
    expect(screen.getByTestId("sidebar-refresh-cancel")).toBeInTheDocument();
    expect(screen.getByTestId("sidebar-refresh")).toHaveTextContent("Refreshing… 42%");
    expect(screen.getByText("Parsing House PTR PDFs")).toBeInTheDocument();
    expect(screen.getByTestId("sidebar-refresh-log")).toBeInTheDocument();
    expect(screen.getByText("Scarico 2024 da https://example.com")).toBeInTheDocument();
    expect(screen.getByTestId("sidebar-refresh-eta")).toHaveTextContent("ETA");
  });

  it("expand button opens the popover panel", async () => {
    const user = userEvent.setup();
    useRefreshStatus.mockReturnValue({
      data: {
        status: "running",
        progress: 20,
        current_step: "download-house-fd",
        phase_label: "Downloading House FD",
        phase_index: 0,
        phase_total: 5,
        sub_progress: 40,
        sub_done: 2,
        sub_total: 5,
        sub_unit: "years",
        eta_seconds: 30,
        started_at: "2026-06-08T21:00:00+00:00",
        log_lines: ["Scarico 2024 da https://example.com"],
      },
    });
    useStartRefresh.mockReturnValue({ mutate: vi.fn(), isPending: false });
    renderSidebar();

    expect(screen.queryByTestId("sidebar-refresh-popover")).not.toBeInTheDocument();
    await user.click(screen.getByTestId("sidebar-refresh-expand"));
    expect(screen.getByTestId("sidebar-refresh-popover")).toBeInTheDocument();
    expect(screen.getByTestId("sidebar-refresh-phase-0")).toBeInTheDocument();
  });

  it("shows success message after refresh completes", () => {
    useRefreshStatus.mockReturnValue({
      data: {
        status: "succeeded",
        progress: 100,
        current_step: "done",
        result: { scope: "ingest-all" },
      },
    });
    useStartRefresh.mockReturnValue({ mutate: vi.fn(), isPending: false });
    renderSidebar();
    expect(screen.getByTestId("sidebar-refresh-success")).toHaveTextContent("Refresh completed");
  });
});
