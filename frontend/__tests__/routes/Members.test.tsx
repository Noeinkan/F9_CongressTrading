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
    {
      member: "Bob",
      trades: 7,
      tickers: 2,
      amount_low: 1000,
      amount_high: 5000,
      chamber: "Senate",
      party: "Republican",
      state: "TX",
    },
    {
      member: "Carol",
      trades: 4,
      tickers: 1,
      amount_low: 1000,
      amount_high: 5000,
      chamber: "House",
      party: "Democrat",
      state: "NY",
    },
  ],
  kpi_sparklines: { members: [], tickers: [], transactions: [] },
};

function renderMembers(initialEntries = ["/"]) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MantineProvider>
        <MemoryRouter initialEntries={initialEntries}>
          <FilterProvider>
            <Members />
          </FilterProvider>
        </MemoryRouter>
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
        rows: [
          {
            ticker: "AAPL",
            issuer_name: "Apple",
            transaction_type: "P",
            transaction_type_label: "Buy",
            transaction_date: "2024-06-01",
            filing_date: "2024-06-10",
            amount_low: 1000,
            amount_high: 5000,
            amount_range_raw: "$1K – $5K",
            return_pct: 12.3,
          },
          {
            ticker: "MSFT",
            issuer_name: "Microsoft",
            transaction_type: "S",
            transaction_type_label: "Sell",
            transaction_date: "2024-03-15",
            filing_date: "2024-03-22",
            amount_low: 1000,
            amount_high: 5000,
            amount_range_raw: "$1K – $5K",
            return_pct: -4.1,
          },
        ],
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

  it("renders leaderboard rows and selects a member on click", async () => {
    const user = userEvent.setup();
    renderMembers();
    await waitFor(() => {
      expect(screen.getByTestId("members-page")).toBeInTheDocument();
    });
    expect(screen.getByTestId("members-empty-profile")).toBeInTheDocument();
    const table = screen.getByTestId("members-leaderboard-table");
    const alice = within(table).getAllByTestId("members-leaderboard-row")[0];
    expect(alice).toBeDefined();
    expect(alice).toHaveTextContent("Alice");
    await user.click(alice!);
    await waitFor(() => {
      expect(screen.getByTestId("members-profile")).toBeInTheDocument();
    });
  });

  it("cycles members with prev/next arrows", async () => {
    const user = userEvent.setup();
    renderMembers(["/?member=Alice"]);
    await waitFor(() => {
      expect(screen.getByTestId("members-nav-position")).toHaveTextContent("1 / 3");
    });

    await user.click(screen.getByTestId("members-next"));
    await waitFor(() => {
      expect(screen.getByTestId("members-nav-position")).toHaveTextContent("2 / 3");
    });
    expect(screen.getByTestId("members-select")).toHaveValue("Bob");

    await user.click(screen.getByTestId("members-next"));
    await waitFor(() => {
      expect(screen.getByTestId("members-nav-position")).toHaveTextContent("3 / 3");
    });
    expect(screen.getByTestId("members-select")).toHaveValue("Carol");

    await user.click(screen.getByTestId("members-next"));
    await waitFor(() => {
      expect(screen.getByTestId("members-nav-position")).toHaveTextContent("1 / 3");
    });
    expect(screen.getByTestId("members-select")).toHaveValue("Alice");

    await user.click(screen.getByTestId("members-prev"));
    await waitFor(() => {
      expect(screen.getByTestId("members-nav-position")).toHaveTextContent("3 / 3");
    });
    expect(screen.getByTestId("members-select")).toHaveValue("Carol");
  });

  it("sorts the leaderboard by column header", async () => {
    const user = userEvent.setup();
    renderMembers();
    await waitFor(() => screen.getByTestId("members-leaderboard-table"));
    await user.click(screen.getByTestId("members-leaderboard-sort-member"));
    const rows = screen.getAllByTestId("members-leaderboard-row");
    expect(rows[0]).toHaveTextContent("Alice");
    await user.click(screen.getByTestId("members-leaderboard-sort-member"));
    const rowsDesc = screen.getAllByTestId("members-leaderboard-row");
    expect(rowsDesc[0]).toHaveTextContent("Carol");
  });

  it("shows profile when member query is set", async () => {
    renderMembers(["/?member=Alice"]);
    await waitFor(() => {
      expect(screen.getByTestId("members-profile")).toBeInTheDocument();
    });
  });

  it("does not block the page shell on summary load when deep-linked", async () => {
    useMembersSummary.mockReturnValue({ data: undefined, isLoading: true, isError: false });
    useMemberTickers.mockReturnValue({ data: undefined, isLoading: true, isError: false });
    renderMembers(["/?member=Alice"]);
    await waitFor(() => {
      expect(screen.getByTestId("members-page")).toBeInTheDocument();
    });
    expect(screen.getByTestId("members-profile-loading")).toBeInTheDocument();
    expect(screen.queryByTestId("page-loading")).not.toBeInTheDocument();
  });

  it("toggles committee view pill", async () => {
    const user = userEvent.setup();
    renderMembers(["/?member=Alice"]);
    await waitFor(() => screen.getByTestId("members-trade-view"));
    await user.click(screen.getByText("Committee relevant"));
    expect(screen.getByTestId("members-committee-card")).toBeInTheDocument();
  });

  it("renders 'n/a' for non-equity trades in the By ticker table", async () => {
    useMemberTickers.mockReturnValue({
      data: {
        member: "Alice",
        kpis: {
          member: "Alice",
          trades: 2,
          tickers: 2,
          disclosed_range: "$1K – $5K",
          chamber: "House",
          party: "Democrat",
          state: "CA",
          sparklines: { transactions: [], tickers: [], disclosed_amount_high: [] },
        },
        rows: [
          {
            ticker: "UTWO",
            issuer_name: "US Treasury Note 2/15/2033",
            transaction_type: "P",
            transaction_type_label: "Buy",
            transaction_date: "2026-03-27",
            filing_date: "2026-04-07",
            amount_low: 1000,
            amount_high: 15000,
            amount_range_raw: "$1K – $15K",
            return_pct: null,
            est_pnl_usd: null,
            is_non_equity: true,
          },
          {
            ticker: "AAPL",
            issuer_name: "Apple Inc.",
            transaction_type: "P",
            transaction_type_label: "Buy",
            transaction_date: "2026-03-25",
            filing_date: "2026-04-02",
            amount_low: 1000,
            amount_high: 15000,
            amount_range_raw: "$1K – $15K",
            return_pct: 12.3,
            est_pnl_usd: 230.0,
            is_non_equity: false,
          },
        ],
      },
      isLoading: false,
      isError: false,
    });
    renderMembers(["/?member=Alice"]);
    await waitFor(() => screen.getByTestId("members-by-ticker-table"));
    const cells = screen.getAllByTestId("members-by-ticker-pnl");
    expect(cells[0]).toHaveTextContent("n/a");
    expect(cells[1]).not.toHaveTextContent("n/a");
    const returns = screen.getAllByTestId("members-by-ticker-return");
    expect(returns[0]).toHaveTextContent("n/a");
    expect(returns[1]).not.toHaveTextContent("n/a");
  });
});
