import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
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
});
