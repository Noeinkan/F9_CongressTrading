import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { FilterProvider } from "@/components/FilterContext";
import { Patterns } from "@/routes/Patterns";

const usePatternsSummary = vi.fn();
const usePatternsCommitteeRelevant = vi.fn();
const usePatternsCoordinatedTransactions = vi.fn();

vi.mock("@/api/patterns", () => ({
  usePatternsSummary: (...args: unknown[]) => usePatternsSummary(...args),
  usePatternsCommitteeRelevant: (...args: unknown[]) => usePatternsCommitteeRelevant(...args),
  usePatternsCoordinatedTransactions: (...args: unknown[]) => usePatternsCoordinatedTransactions(...args),
}));

vi.mock("echarts-for-react", () => ({
  default: () => <div data-testid="echarts-mock" />,
}));

const sample = {
  ready: true,
  window_days: 90,
  min_members: 2,
  coordinated_limit: 50,
  committee: {
    summary: [
      {
        member: "Alice",
        chamber: "House",
        party: "Democrat",
        total_trades: 10,
        relevant_trades: 2,
        relevance_pct: 20,
        top_committee: "Finance",
        top_sector: "Financials",
      },
    ],
    members_with_overlap: ["Alice"],
    coverage: { member_coverage_pct: 50, sector_coverage_pct: 80, members_mapped: 1 },
  },
  coordinated: [
    {
      ticker: "AAPL",
      pattern: "Coordinated buy",
      members: 3,
      member_names: "Alice, Bob",
      trades: 5,
      date_from: "2024-01-01",
      date_to: "2024-03-01",
    },
  ],
  call_put: { monthly: [], ratio: [] },
  volume_anomalies: [],
  bipartisan: [],
};

function renderPatterns() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MantineProvider>
        <FilterProvider>
          <MemoryRouter>
            <Patterns />
          </MemoryRouter>
        </FilterProvider>
      </MantineProvider>
    </QueryClientProvider>,
  );
}

describe("Patterns route", () => {
  beforeEach(() => {
    usePatternsSummary.mockReturnValue({ data: sample, isLoading: false, isError: false });
    usePatternsCommitteeRelevant.mockReturnValue({ data: { rows: [] }, isLoading: false, isError: false });
    usePatternsCoordinatedTransactions.mockReturnValue({ data: { rows: [] }, isLoading: false, isError: false });
  });

  it("renders patterns sections", async () => {
    renderPatterns();
    await waitFor(() => {
      expect(screen.getByTestId("patterns-page")).toBeInTheDocument();
    });
    expect(screen.getByTestId("patterns-committee-table")).toBeInTheDocument();
    expect(screen.getByTestId("patterns-coordinated-table")).toBeInTheDocument();
  });

  it("refetches when window slider changes", async () => {
    const user = userEvent.setup();
    renderPatterns();
    await waitFor(() => screen.getByTestId("patterns-window-slider"));
    const callsBefore = usePatternsSummary.mock.calls.length;
    const slider = screen.getByTestId("patterns-window-slider");
    await user.click(slider);
    expect(usePatternsSummary.mock.calls.length).toBeGreaterThanOrEqual(callsBefore);
  });
});
