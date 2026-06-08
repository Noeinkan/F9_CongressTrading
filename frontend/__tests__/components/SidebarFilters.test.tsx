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

vi.mock("@/api/refresh", () => ({
  useRefreshStatus: (...args: unknown[]) => useRefreshStatus(...args),
  useStartRefresh: (...args: unknown[]) => useStartRefresh(...args),
  useCancelRefresh: (...args: unknown[]) => useCancelRefresh(...args),
}));

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

  it("clicking refresh triggers start mutation", async () => {
    const user = userEvent.setup();
    const mutate = vi.fn();
    useStartRefresh.mockReturnValue({ mutate, isPending: false });
    renderSidebar();
    await user.click(screen.getByTestId("sidebar-refresh"));
    expect(mutate).toHaveBeenCalledTimes(1);
  });

  it("shows progress and cancel while refresh is running", () => {
    useRefreshStatus.mockReturnValue({
      data: {
        status: "running",
        progress: 42,
        current_step: "ingest-house",
        log_lines: ["Scarico 2024 da https://example.com", "Trovati 120 PDF PTR"],
      },
    });
    useStartRefresh.mockReturnValue({ mutate: vi.fn(), isPending: false });
    renderSidebar();
    expect(screen.getByTestId("sidebar-refresh-progress")).toBeInTheDocument();
    expect(screen.getByTestId("sidebar-refresh-cancel")).toBeInTheDocument();
    expect(screen.getByTestId("sidebar-refresh")).toHaveTextContent("Refreshing… 42%");
    expect(screen.getByText("ingest-house")).toBeInTheDocument();
    expect(screen.getByTestId("sidebar-refresh-log")).toBeInTheDocument();
    expect(screen.getByText("Scarico 2024 da https://example.com")).toBeInTheDocument();
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
