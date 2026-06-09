import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";

import { FilterProvider } from "@/components/FilterContext";
import { Home } from "@/routes/Home";

const useHomeSummary = vi.fn();
const useTickerDrilldown = vi.fn();

vi.mock("@/api/home", () => ({
  useHomeSummary: (...args: unknown[]) => useHomeSummary(...args),
  netTradeCsvUrl: () => "/api/home/net_trade.csv?lookback=1",
}));

vi.mock("@/api/tickerDrilldown", () => ({
  useTickerDrilldown: (...args: unknown[]) => useTickerDrilldown(...args),
}));

vi.mock("echarts-for-react", () => ({
  default: ({ "data-testid": testId }: { "data-testid"?: string }) => (
    <div data-testid={testId ?? "echarts-mock"} />
  ),
}));

const sampleData = {
  ready: true,
  hero: {
    transaction_source: "sqlite",
    review_source: "sqlite",
    total_transactions: 100,
    total_members: 10,
    tracked_tickers: 5,
    open_reviews: 2,
    avg_confidence: 0.8,
    avg_confidence_label: "80%",
    active_chambers: "House, Senate",
    amount_low_total: 1000,
    amount_high_total: 5000,
    disclosed_range: "$1K – $5K",
    coverage_from: "2024-01-01",
    coverage_to: "2024-12-31",
    latest_filing: "2024-12-01",
  },
  kpis: [
    {
      key: "transactions",
      label: "Transactions",
      value: 100,
      detail: "Rows",
      sparkline: [{ month: "2024-01", value: 10 }],
      delta: { value: 1, percent: false, label: "+1" },
    },
  ],
  latest_transactions: [
    {
      member: "Alice",
      chamber: "House",
      party: "D",
      ticker: "AAPL",
      issuer_name: "Apple Inc.",
      transaction_type_label: "Buy",
      transaction_date: "2024-06-01",
      amount_range_raw: "$1K – $15K",
      filing_date: "2024-06-15",
      disclosure_url: "",
    },
    {
      member: "Bob",
      chamber: "House",
      party: "R",
      ticker: "",
      transaction_type_label: "Buy",
      transaction_date: "2024-06-02",
      amount_range_raw: "$1K – $15K",
      filing_date: "2024-06-16",
      disclosure_url: "",
    },
    {
      member: "Carol",
      chamber: "Senate",
      party: "D",
      ticker: "MSFT",
      issuer_name: "Microsoft Corp.",
      transaction_type_label: "Sell (partial)",
      transaction_date: "2024-06-03",
      amount_range_raw: "$50,001 - $100,000",
      filing_date: "2024-06-17",
      disclosure_url: "",
    },
    {
      member: "Dan",
      chamber: "House",
      party: "R",
      ticker: "TSLA",
      issuer_name: "Tesla, Inc.",
      transaction_type_label: "Buy",
      transaction_date: "2024-05-28",
      amount_range_raw: "$1,001 - $15,000",
      filing_date: "2024-06-10",
      disclosure_url: "",
    },
  ],
  breakdown: {
    by_chamber: [{ chamber: "House", transactions: 80 }],
    by_type: [{ transaction_type_label: "Buy", transactions: 60 }],
  },
  monthly_activity: [{ month: "2024-06", transactions: 10, amount_low: 100, amount_high: 500 }],
  top_members: [{ member: "Alice", transactions: 20, amount_low: 100, amount_high: 500, disclosed_range: "$100 – $500" }],
  top_tickers: [{ ticker: "AAPL", transactions: 15, amount_low: 100, amount_high: 500, disclosed_range: "$100 – $500" }],
  members_leaderboard: [
    {
      member: "Alice",
      trades: 20,
      tickers: 5,
      amount_low: 100,
      amount_high: 500,
      chamber: "House",
      party: "Democrat",
      state: "CA",
    },
  ],
  net_trade_amounts: [
    {
      ticker: "AAPL",
      first_trade: "2024-01-01",
      last_trade: "2024-06-01",
      direction: "Net buying",
      net_amount: 1000,
      net_label: "$1.0K",
      buy_label: "$2.0K",
      sell_label: "$1.0K",
      trades: 5,
    },
  ],
  tickers_available: ["AAPL", "MSFT"],
};

function renderHome(initialEntries = ["/"]) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MantineProvider>
        <FilterProvider>
          <MemoryRouter initialEntries={initialEntries}>
            <Home />
          </MemoryRouter>
        </FilterProvider>
      </MantineProvider>
    </QueryClientProvider>,
  );
}

describe("Home route", () => {
  beforeEach(() => {
    useHomeSummary.mockReset();
    useTickerDrilldown.mockReset();
    useTickerDrilldown.mockReturnValue({
      data: { ticker_timeline: [], ticker_3d: [], ticker_cumulative: [] },
      isLoading: false,
      isError: false,
    });
  });

  it("shows loading state", () => {
    useHomeSummary.mockReturnValue({ data: undefined, isLoading: true, isError: false });
    renderHome();
    expect(screen.getByTestId("page-loading")).toBeInTheDocument();
  });

  it("renders hero and KPI strip when data resolves", async () => {
    useHomeSummary.mockReturnValue({ data: sampleData, isLoading: false, isError: false });
    renderHome();
    await waitFor(() => {
      expect(screen.getByTestId("home-page")).toBeInTheDocument();
    });
    expect(screen.getByTestId("home-hero")).toBeInTheDocument();
    expect(screen.getByTestId("kpi-tile-transactions")).toBeInTheDocument();
  });

  it("renders the members leaderboard with a clickable link to the profile", async () => {
    useHomeSummary.mockReturnValue({ data: sampleData, isLoading: false, isError: false });
    renderHome();
    await waitFor(() => {
      expect(screen.getByTestId("home-leaderboard-table")).toBeInTheDocument();
    });
    const row = screen.getByTestId("home-leaderboard-row");
    const link = within(row).getByRole("link", { name: "Alice" });
    expect(link).toHaveAttribute("href", "/members?member=Alice");
  });

  it("does not call drilldown hook until ticker is available", () => {
    useHomeSummary.mockReturnValue({ data: sampleData, isLoading: false, isError: false });
    renderHome();
    expect(useTickerDrilldown).toHaveBeenCalledWith("AAPL", expect.any(Object));
  });

  it("renders the latest activity table with issuer name next to the ticker", async () => {
    useHomeSummary.mockReturnValue({ data: sampleData, isLoading: false, isError: false });
    renderHome();
    await waitFor(() => {
      expect(screen.getByTestId("home-latest-table")).toBeInTheDocument();
    });
    const table = screen.getByTestId("home-latest-table");
    expect(within(table).getByText("AAPL")).toBeInTheDocument();
    expect(within(table).getByText("Apple Inc.")).toBeInTheDocument();
    expect(within(table).getByText("—")).toBeInTheDocument();
  });

  it("toggles net trade chart/table and enables CSV only in table view", async () => {
    useHomeSummary.mockReturnValue({ data: sampleData, isLoading: false, isError: false });
    renderHome(["/?net_view=chart"]);
    const user = userEvent.setup();
    expect(screen.getByTestId("net-trade-chart")).toBeInTheDocument();
    expect(screen.getByTestId("home-net-download")).toHaveAttribute("data-disabled", "true");
    await user.click(screen.getByText("Table"));
    expect(screen.getByTestId("home-net-table")).toBeInTheDocument();
    expect(screen.getByTestId("home-net-download")).not.toHaveAttribute("data-disabled", "true");
  });

  it("renders a clickable ticker link that navigates to the Tickers page", async () => {
    useHomeSummary.mockReturnValue({ data: sampleData, isLoading: false, isError: false });
    renderHome();
    await waitFor(() => {
      expect(screen.getByTestId("home-latest-table")).toBeInTheDocument();
    });
    const aaplLinks = screen.getAllByTestId("home-latest-ticker");
    expect(aaplLinks.length).toBeGreaterThan(0);
    // The AAPL ticker row should link to /tickers?ticker=AAPL.
    const aaplLink = aaplLinks.find((el) => el.textContent === "AAPL");
    expect(aaplLink).toBeDefined();
    expect(aaplLink).toHaveAttribute("href", "/tickers?ticker=AAPL");
  });

  it("color-codes the Type badge: buy rows render distinctly from sell rows", async () => {
    useHomeSummary.mockReturnValue({ data: sampleData, isLoading: false, isError: false });
    renderHome();
    await waitFor(() => {
      expect(screen.getByTestId("home-latest-table")).toBeInTheDocument();
    });
    const typeBadges = screen.getAllByTestId("home-latest-type");
    const buys = typeBadges.filter((b) => b.getAttribute("data-direction") === "buy");
    const sells = typeBadges.filter((b) => b.getAttribute("data-direction") === "sell");
    expect(buys.length).toBeGreaterThan(0);
    expect(sells.length).toBeGreaterThan(0);
    // Mantine maps the `color` prop to a CSS variable on the Badge root. The
    // buy/sell badges should differ in either className, data attributes, or
    // inline style — assert they are not byte-identical.
    const firstBuy = buys[0];
    const firstSell = sells[0];
    expect(firstBuy).toBeDefined();
    expect(firstSell).toBeDefined();
    const buySig = `${firstBuy!.className}|${firstBuy!.getAttribute("data-direction") ?? ""}|${
      firstBuy!.getAttribute("style") ?? ""
    }`;
    const sellSig = `${firstSell!.className}|${firstSell!.getAttribute("data-direction") ?? ""}|${
      firstSell!.getAttribute("style") ?? ""
    }`;
    expect(buySig).not.toBe(sellSig);
  });

  it("applies a higher opacity to the largest disclosed range than to a small one", async () => {
    useHomeSummary.mockReturnValue({ data: sampleData, isLoading: false, isError: false });
    renderHome();
    await waitFor(() => {
      expect(screen.getByTestId("home-latest-table")).toBeInTheDocument();
    });
    const rows = screen.getAllByTestId("home-latest-row");
    const danRow = rows.find((r) => r.textContent?.includes("Dan"));
    const carolRow = rows.find((r) => r.textContent?.includes("Carol"));
    expect(danRow).toBeDefined();
    expect(carolRow).toBeDefined();
    // Carol's range high is $100,000; Dan's high is $15,000. Carol should be
    // rendered with a higher opacity.
    const carolBadge = within(carolRow!).getByTestId("home-latest-type");
    const danBadge = within(danRow!).getByTestId("home-latest-type");
    const carolOpacity = Number.parseFloat(carolBadge.style.opacity);
    const danOpacity = Number.parseFloat(danBadge.style.opacity);
    expect(carolOpacity).toBeGreaterThan(danOpacity);
  });

  it("respects the Rows size selector", async () => {
    useHomeSummary.mockReturnValue({ data: sampleData, isLoading: false, isError: false });
    renderHome();
    const user = userEvent.setup();
    await waitFor(() => {
      expect(screen.getByTestId("home-latest-table")).toBeInTheDocument();
    });
    // 4 rows in the fixture, default size is 25, so all 4 should render.
    expect(screen.getAllByTestId("home-latest-row")).toHaveLength(4);
    // Click "100" — still 4 rows.
    await user.click(screen.getByRole("radio", { name: "100" }));
    expect(screen.getAllByTestId("home-latest-row")).toHaveLength(4);
  });

  it("sorts the latest table by member when the Member header is clicked", async () => {
    useHomeSummary.mockReturnValue({ data: sampleData, isLoading: false, isError: false });
    renderHome();
    const user = userEvent.setup();
    await waitFor(() => {
      expect(screen.getByTestId("home-latest-table")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("home-latest-sort-member"));
    let memberCells = screen
      .getAllByTestId("home-latest-row")
      .map((row) => row.querySelector("td")?.textContent);
    // Default sort key is transaction_date desc, then we click Member once -> asc.
    expect(memberCells).toEqual(["Alice", "Bob", "Carol", "Dan"]);
    // Click again -> desc.
    await user.click(screen.getByTestId("home-latest-sort-member"));
    memberCells = screen
      .getAllByTestId("home-latest-row")
      .map((row) => row.querySelector("td")?.textContent);
    expect(memberCells).toEqual(["Dan", "Carol", "Bob", "Alice"]);
  });
});
