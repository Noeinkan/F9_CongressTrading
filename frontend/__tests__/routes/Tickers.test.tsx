import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { FilterProvider } from "@/components/FilterContext";
import { Tickers } from "@/routes/Tickers";

const useTickersList = vi.fn();
const useTickerProfile = vi.fn();
const useTickerPriceOverlay = vi.fn();
const useTickerMemberTimeline = vi.fn();
const useTickerCumulativeExposure = vi.fn();

vi.mock("@/api/tickers", () => ({
  useTickersList: (...args: unknown[]) => useTickersList(...args),
  useTickerProfile: (...args: unknown[]) => useTickerProfile(...args),
  useTickerPriceOverlay: (...args: unknown[]) => useTickerPriceOverlay(...args),
  useTickerMemberTimeline: (...args: unknown[]) => useTickerMemberTimeline(...args),
  useTickerCumulativeExposure: (...args: unknown[]) => useTickerCumulativeExposure(...args),
}));

vi.mock("echarts-for-react", () => ({
  default: () => <div data-testid="echarts-mock" />,
}));

function renderTickers(initialEntries = ["/?ticker=AAPL"]) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MantineProvider>
        <FilterProvider>
          <MemoryRouter initialEntries={initialEntries}>
            <Tickers />
          </MemoryRouter>
        </FilterProvider>
      </MantineProvider>
    </QueryClientProvider>,
  );
}

describe("Tickers route", () => {
  beforeEach(() => {
    useTickersList.mockReturnValue({
      data: {
        ready: true,
        rows: [{ ticker: "AAPL" }],
        total: 1,
        page: 1,
        page_size: 200,
        total_pages: 1,
        sort: { column: "trades", order: "desc" },
        search: "",
        source: "sqlite",
      },
      isLoading: false,
      isError: false,
    });
    useTickerProfile.mockReturnValue({
      data: {
        ready: true,
        ticker: "AAPL",
        issuer: { issuer_name: "Apple Inc", ticker: "AAPL", sector: "Tech", industry: "", asset_type: "" },
        kpis: { trades: 5, members: 2, buy: 3, sell: 2, disclosed_range: "$1K – $5K" },
        disclosed_range: "$1K – $5K",
        members: [{ member: "Alice", buy: 1, sell: 0, call: 0, put: 0, exchange: 0, trades: 1, disclosed_range: "$1K", first_trade: null, last_trade: null, chamber: "House", party: "D" }],
        transactions: [],
        transactions_total: 0,
        transactions_limit: 200,
        source: "sqlite",
      },
      isLoading: false,
      isError: false,
    });
    useTickerPriceOverlay.mockReturnValue({
      data: { ready: false, ticker: "AAPL", bars: [], trades: [] },
      isLoading: false,
      isError: false,
    });
    useTickerMemberTimeline.mockReturnValue({
      data: { ticker: "AAPL", members: ["Alice"], rows: [] },
      isLoading: false,
      isError: false,
    });
    useTickerCumulativeExposure.mockReturnValue({
      data: { ticker: "AAPL", members: [], truncated: false, rows: [] },
      isLoading: false,
      isError: false,
    });
  });

  it("renders ticker profile sections", async () => {
    renderTickers();
    await waitFor(() => {
      expect(screen.getByTestId("tickers-page")).toBeInTheDocument();
    });
    expect(screen.getByTestId("tickers-who-traded")).toBeInTheDocument();
    expect(screen.getByTestId("tickers-cumulative")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Alice" })).toHaveAttribute(
      "href",
      "/members?member=Alice",
    );
  });

  it("renders 'n/a' for non-equity trades in the Trade history table", async () => {
    useTickerProfile.mockReturnValueOnce({
      data: {
        ready: true,
        ticker: "UTWO",
        issuer: { issuer_name: "US Treasury Note 2/15/2033", ticker: "UTWO", sector: "", industry: "", asset_type: "" },
        kpis: { trades: 1, members: 1, buy: 1, sell: 0, disclosed_range: "$1K – $15K" },
        disclosed_range: "$1K – $15K",
        members: [],
        transactions: [
          {
            member: "Alice",
            chamber: "House",
            party: "D",
            ticker: "UTWO",
            transaction_type: "P",
            transaction_type_label: "Buy",
            transaction_date: "2026-03-27",
            filing_date: "2026-04-07",
            amount_low: 1000,
            amount_high: 15000,
            amount_range_raw: "$1K – $15K",
            issuer_name: "US Treasury Note 2/15/2033",
            return_pct: null,
            est_pnl_usd: null,
            is_non_equity: true,
          },
        ],
        transactions_total: 1,
        transactions_limit: 200,
        source: "sqlite",
      },
      isLoading: false,
      isError: false,
    });
    renderTickers();
    await waitFor(() => screen.getByTestId("tickers-trade-history-table"));
    const cell = screen.getByTestId("tickers-trade-history-return");
    expect(cell).toHaveTextContent("n/a");
  });

  it("links to the SearchForAlpha Lab dashboard with the active ticker", async () => {
    renderTickers();
    await waitFor(() => screen.getByTestId("tickers-page"));
    const link = screen.getByTestId("tickers-open-searchforalpha");
    expect(link).toHaveAttribute("href", "http://127.0.0.1:8060/?ticker=AAPL");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("disables the SearchForAlpha button when no ticker is selected", async () => {
    useTickersList.mockReturnValueOnce({
      data: { ready: true, rows: [], total: 0, page: 1, page_size: 200, total_pages: 1, sort: { column: "trades", order: "desc" }, search: "", source: "sqlite" },
      isLoading: false,
      isError: false,
    });
    renderTickers(["/"]);
    await waitFor(() => screen.getByTestId("tickers-page"));
    const link = screen.getByTestId("tickers-open-searchforalpha");
    expect(link).toHaveAttribute("href", "http://127.0.0.1:8060/");
    expect(link).toHaveAttribute("data-disabled", "true");
    expect(link).toHaveAttribute("aria-disabled", "true");
  });

  it("filters the trade history table by amount-range bucket", async () => {
    useTickerProfile.mockReturnValue({
      data: {
        ready: true,
        ticker: "AAPL",
        issuer: { issuer_name: "Apple Inc", ticker: "AAPL", sector: "Tech", industry: "", asset_type: "" },
        kpis: { trades: 3, members: 2, buy: 2, sell: 1, disclosed_range: "$1K – $1M" },
        disclosed_range: "$1K – $1M",
        members: [],
        transactions: [
          {
            member: "Alice",
            chamber: "House",
            party: "D",
            ticker: "AAPL",
            transaction_type: "P",
            transaction_type_label: "Buy",
            transaction_date: "2026-01-10",
            filing_date: "2026-01-20",
            amount_low: 1000,
            amount_high: 15000,
            amount_range_raw: "$1K – $15K",
            issuer_name: "Apple Inc",
            return_pct: 0.05,
            est_pnl_usd: 250,
            is_non_equity: false,
          },
          {
            member: "Bob",
            chamber: "Senate",
            party: "R",
            ticker: "AAPL",
            transaction_type: "S",
            transaction_type_label: "Sell",
            transaction_date: "2026-02-05",
            filing_date: "2026-02-15",
            amount_low: 500001,
            amount_high: 1000000,
            amount_range_raw: "$500K – $1M",
            issuer_name: "Apple Inc",
            return_pct: 0.12,
            est_pnl_usd: 90000,
            is_non_equity: false,
          },
          {
            member: "Carol",
            chamber: "House",
            party: "D",
            ticker: "AAPL",
            transaction_type: "P",
            transaction_type_label: "Buy",
            transaction_date: "2026-03-01",
            filing_date: "2026-03-12",
            amount_low: 250001,
            amount_high: 500000,
            amount_range_raw: "$250K – $500K",
            issuer_name: "Apple Inc",
            return_pct: -0.02,
            est_pnl_usd: -8000,
            is_non_equity: false,
          },
        ],
        transactions_total: 3,
        transactions_limit: 200,
        source: "sqlite",
      },
      isLoading: false,
      isError: false,
    });
    const user = userEvent.setup();
    renderTickers();
    await waitFor(() => screen.getByTestId("tickers-trade-history-table"));
    expect(screen.getAllByTestId("tickers-trade-history-row")).toHaveLength(3);

    // Open the filter accordion and pick the $500K – $1M bucket.
    await user.click(
      screen.getByRole("button", { name: /Filter by disclosed amount range/i }),
    );
    await user.click(
      screen.getByTestId("tickers-amount-range-filter-item-500k-1m"),
    );

    const rows = screen.getAllByTestId("tickers-trade-history-row");
    expect(rows).toHaveLength(1);
    const onlyRow = rows[0]!;
    expect(within(onlyRow).getByText("Bob")).toBeInTheDocument();
    expect(within(onlyRow).getByText("$500K – $1M")).toBeInTheDocument();

    // Clear filter -> all rows return.
    await user.click(screen.getByTestId("tickers-amount-range-filter-reset"));
    expect(screen.getAllByTestId("tickers-trade-history-row")).toHaveLength(3);
  });
});
