import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { FilterProvider } from "@/components/FilterContext";
import { Members } from "@/routes/Members";

const useMembersSummary = vi.fn();
const useMemberTickers = vi.fn();
const useMemberCommitteeRelevant = vi.fn();
const useMemberActivityTimeline = vi.fn();

vi.mock("@/api/members", () => ({
  useMembersSummary: (...args: unknown[]) => useMembersSummary(...args),
  useMemberTickers: (...args: unknown[]) => useMemberTickers(...args),
  useMemberCommitteeRelevant: (...args: unknown[]) => useMemberCommitteeRelevant(...args),
  useMemberActivityTimeline: (...args: unknown[]) => useMemberActivityTimeline(...args),
}));

vi.mock("echarts-for-react", () => ({
  default: () => <div data-testid="echarts-mock" />,
}));

const summary = {
  ready: true,
  transaction_source: "sqlite",
  leaderboard: [
    {
      member: "Alice",
      trades: 10,
      tickers: 3,
      amount_low: 1000,
      amount_high: 5000,
      chamber: "House",
      party: "Democrat",
      state: "CA",
    },
  ],
  kpi_sparklines: { members: [], tickers: [], transactions: [] },
};

function renderMembers(initialEntries = ["/"]) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MantineProvider>
        <FilterProvider>
          <MemoryRouter initialEntries={initialEntries}>
            <Members />
          </MemoryRouter>
        </FilterProvider>
      </MantineProvider>
    </QueryClientProvider>,
  );
}

describe("Members route", () => {
  beforeEach(() => {
    useMembersSummary.mockReturnValue({ data: summary, isLoading: false, isError: false });
    useMemberTickers.mockReturnValue({
      data: {
        member: "Alice",
        kpis: {
          member: "Alice",
          trades: 10,
          tickers: 3,
          disclosed_range: "$1K – $5K",
          chamber: "House",
          party: "Democrat",
          state: "CA",
          sparklines: { transactions: [], tickers: [], disclosed_amount_high: [] },
        },
        rows: [{ ticker: "AAPL", trades: 5, buy: 3, sell: 2, call: 0, put: 0, exchange: 0, disclosed_range: "$1K", first_trade: "2024-01-01", last_trade: "2024-06-01" }],
      },
      isLoading: false,
      isError: false,
    });
    useMemberCommitteeRelevant.mockReturnValue({ data: { rows: [] }, isLoading: false, isError: false });
    useMemberActivityTimeline.mockReturnValue({
      data: { rows: [], tickers: [], truncated: false, truncate_note: "" },
      isLoading: false,
      isError: false,
    });
  });

  it("renders mini-leaderboard chips with a clickable member", async () => {
    const user = userEvent.setup();
    renderMembers();
    await waitFor(() => {
      expect(screen.getByTestId("members-page")).toBeInTheDocument();
    });
    const chips = screen.getByTestId("members-browse-chips");
    expect(chips).toBeInTheDocument();
    const alice = within(chips).getByTestId("members-browse-chip");
    expect(alice).toHaveTextContent("Alice");
    await user.click(alice);
    await waitFor(() => {
      expect(screen.getByTestId("members-profile")).toBeInTheDocument();
    });
  });

  it("shows profile when member query is set", async () => {
    renderMembers(["/?member=Alice"]);
    await waitFor(() => {
      expect(screen.getByTestId("members-profile")).toBeInTheDocument();
    });
  });

  it("toggles committee view pill", async () => {
    const user = userEvent.setup();
    renderMembers(["/?member=Alice"]);
    await waitFor(() => screen.getByTestId("members-trade-view"));
    await user.click(screen.getByText("Committee relevant"));
    expect(screen.getByTestId("members-committee-card")).toBeInTheDocument();
  });
});
