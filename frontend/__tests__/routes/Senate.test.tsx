import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { SenateSummaryResponse } from "@/api/types";
import { FilterProvider } from "@/components/FilterContext";
import { Senate } from "@/routes/Senate";

const useSenateSummary = vi.fn();

vi.mock("@/api/senate", () => ({
  useSenateSummary: (...args: unknown[]) => useSenateSummary(...args),
}));

vi.mock("echarts-for-react", () => ({
  default: ({ "data-testid": testId }: { "data-testid"?: string }) => (
    <div data-testid={testId ?? "echarts-mock"} />
  ),
}));

const sampleData: SenateSummaryResponse = {
  ready: true,
  hero: {
    transaction_source: "sqlite",
    review_source: "sqlite",
    total_transactions: 3,
    total_members: 2,
    tracked_tickers: 3,
    open_reviews: 0,
    avg_confidence: 0.99,
    avg_confidence_label: "99%",
    active_chambers: "Senate",
    amount_low_total: 66003,
    amount_high_total: 165000,
    disclosed_range: "$66.0K – $165.0K",
    coverage_from: "2026-03-01",
    coverage_to: "2026-06-20",
    latest_filing: "2026-07-02",
  },
  kpis: [
    { key: "transactions", label: "Transactions", value: 3, detail: "Rows", sparkline: [], delta: null },
    { key: "members", label: "Members", value: 2, detail: "Distinct filers", sparkline: [], delta: null },
    { key: "open_reviews", label: "Open reviews", value: 0, detail: "Queue", sparkline: [], delta: null },
  ],
  latest_transactions: [
    {
      member: "Gary C Peters",
      chamber: "Senate",
      party: "Democrat",
      ticker: "NVDA",
      issuer_name: "NVIDIA Corp",
      transaction_type_label: "Buy",
      transaction_date: "2026-06-20",
      amount_range_raw: "$50,001 - $100,000",
      filing_date: "2026-07-02",
      disclosure_url: "",
    },
  ],
  breakdown: { by_chamber: [{ chamber: "Senate", transactions: 3 }], by_type: [] },
  monthly_activity: [],
  top_members: [],
  top_tickers: [],
  members_leaderboard: [],
  net_trade_amounts: [],
  tickers_available: ["NVDA"],
  senate_rows_all_time: 3,
  coverage: { senators: 2, filings: 2, first_filing: "2026-06-30", latest_filing: "2026-07-02" },
  timeliness: {
    deadline_days: 45,
    dated_trades: 3,
    late_trades: 1,
    late_share: 1 / 3,
    late_share_label: "33%",
    median_delay_days: 20,
    late_filers: [{ member: "John R Curtis", trades: 2, late_trades: 1, worst_days_late: 76 }],
  },
  filings: [
    {
      member: "Gary C Peters",
      party: "Democrat",
      state: "MI",
      doc_id: "sen-2",
      filing_date: "2026-07-02",
      trades: 1,
      tickers: 1,
      amount_low: 50001,
      amount_high: 100000,
      disclosed_range: "$50.0K – $100.0K",
      traded_from: "2026-06-20",
      traded_to: "2026-06-20",
    },
  ],
};

function renderSenate() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MantineProvider>
        <MemoryRouter initialEntries={["/senate"]}>
          <FilterProvider>
            <Senate />
          </FilterProvider>
        </MemoryRouter>
      </MantineProvider>
    </QueryClientProvider>,
  );
}

describe("Senate route", () => {
  beforeEach(() => {
    useSenateSummary.mockReset();
    useSenateSummary.mockReturnValue({ data: sampleData, isLoading: false, isError: false });
  });

  it("shows coverage and explains why there are no PDF links", () => {
    renderSenate();
    const header = screen.getByTestId("senate-header");
    expect(header).toHaveTextContent(/Senators with trades\s*2/);
    expect(header).toHaveTextContent("30/06/2026 – 02/07/2026");
    expect(screen.getByTestId("senate-no-pdf-note")).toHaveTextContent(/accept its terms/);
  });

  it("relabels members as senators, drops the review KPI and adds lateness", () => {
    renderSenate();
    expect(screen.getByTestId("kpi-tile-members")).toHaveTextContent("Senators");
    expect(screen.queryByTestId("kpi-tile-open_reviews")).not.toBeInTheDocument();
    expect(screen.getByTestId("kpi-tile-late")).toHaveTextContent("33%");
    expect(screen.getByTestId("kpi-tile-late")).toHaveTextContent(/1 of 3 trades past the 45-day deadline/);
  });

  it("links senators to their profile instead of a source document", () => {
    renderSenate();
    const [filing] = screen.getAllByTestId("senate-filing-row");
    if (!filing) throw new Error("no filing row rendered");
    const link = within(filing).getByRole("link", { name: "Gary C Peters" });
    expect(link).toHaveAttribute("href", "/members?member=Gary%20C%20Peters");
    expect(within(filing).getByText("D-MI")).toBeInTheDocument();
    expect(screen.getByTestId("senate-latest-table")).not.toHaveTextContent(/PDF/);
  });

  it("lists late filers with days past the deadline", () => {
    renderSenate();
    const [row] = screen.getAllByTestId("senate-late-row");
    expect(row).toHaveTextContent("John R Curtis");
    expect(row).toHaveTextContent("1 of 2");
    expect(row).toHaveTextContent("76 days late");
  });

  it("tells an empty database apart from an empty period", () => {
    useSenateSummary.mockReturnValue({
      data: { ...sampleData, senate_rows_all_time: 0, hero: { ...sampleData.hero, total_transactions: 0 } },
      isLoading: false,
      isError: false,
    });
    const { unmount } = renderSenate();
    expect(screen.getByTestId("senate-empty")).toHaveTextContent(/No Senate filings ingested yet/);
    unmount();

    useSenateSummary.mockReturnValue({
      data: { ...sampleData, hero: { ...sampleData.hero, total_transactions: 0 } },
      isLoading: false,
      isError: false,
    });
    renderSenate();
    expect(screen.getByTestId("senate-empty-period")).toHaveTextContent(/3 loaded so far/);
    expect(screen.queryByTestId("senate-header")).not.toBeInTheDocument();
  });
});
