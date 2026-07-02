import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { Executive } from "@/routes/Executive";

const useExecutiveFilers = vi.fn();
const useExecutiveFilings = vi.fn();
const useExecutiveHoldings = vi.fn();
const useExecutiveTransactions = vi.fn();

vi.mock("@/api/executive", () => ({
  useExecutiveFilers: (...args: unknown[]) => useExecutiveFilers(...args),
  useExecutiveFilings: (...args: unknown[]) => useExecutiveFilings(...args),
  useExecutiveHoldings: (...args: unknown[]) => useExecutiveHoldings(...args),
  useExecutiveTransactions: (...args: unknown[]) => useExecutiveTransactions(...args),
}));

const sampleFiler = {
  filer_name: "Donald J. Trump",
  latest_filing_date: "2024-08-15",
  filing_count: 3,
  transaction_count: 12,
};

const sampleFiling = {
  filing_type: "278-T",
  filing_date: "2024-08-15",
  doc_id: "oge-2024-q2-trump",
  source_url: "https://oge.example/2024-q2.pdf",
  raw_document_path: "data/raw/executive/trump-2024-q2.pdf",
  transaction_count: 4,
};

const sampleTransaction = {
  chamber: "Executive",
  member: "Donald J. Trump",
  filing_type: "278-T",
  filing_date: "2024-08-15",
  transaction_date: "2024-07-30",
  asset_name_raw: "Apple Inc Common Stock",
  asset_name_normalized: "Apple Inc.",
  asset_type: "Stock",
  issuer_name: "Apple Inc.",
  ticker: "AAPL",
  sector: "Technology",
  industry: "Consumer Electronics",
  transaction_type: "P",
  transaction_type_label: "Buy",
  amount_low: 50001,
  amount_high: 100000,
  amount_range_raw: "$50,001 – $100,000",
  confidence_score: 0.95,
  review_status: "approved",
  source_url: "https://oge.example/2024-q2.pdf",
  raw_document_path: "data/raw/executive/trump-2024-q2.pdf",
  disclosure_url: "https://oge.example/2024-q2.pdf#tx-1",
  doc_id: "oge-2024-q2-trump",
};

const loadedMocks = () => {
  useExecutiveFilers.mockReturnValue({
    data: [sampleFiler],
    isLoading: false,
    isError: false,
  });
  useExecutiveFilings.mockReturnValue({
    data: [sampleFiling],
    isLoading: false,
    isError: false,
  });
  useExecutiveHoldings.mockReturnValue({
    data: [
      {
        asset_name: "Trump Tower",
        value_range: "$5,000,001 – $25,000,000",
        owner_type: "filer",
        asset_type: "Real Estate",
        source_url: "https://oge.example/2024-278e.pdf",
        filing_date: "2024-06-30",
      },
    ],
    isLoading: false,
    isError: false,
  });
  useExecutiveTransactions.mockReturnValue({
    data: { rows: [sampleTransaction], total: 1 },
    isLoading: false,
    isError: false,
  });
};

const emptyMocks = () => {
  useExecutiveFilers.mockReturnValue({
    data: [],
    isLoading: false,
    isError: false,
  });
  useExecutiveFilings.mockReturnValue({
    data: [],
    isLoading: false,
    isError: false,
  });
  useExecutiveHoldings.mockReturnValue({
    data: [],
    isLoading: false,
    isError: false,
  });
  useExecutiveTransactions.mockReturnValue({
    data: { rows: [], total: 0 },
    isLoading: false,
    isError: false,
  });
};

function renderExecutive(initialEntries = ["/executive"]) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MantineProvider>
        <MemoryRouter initialEntries={initialEntries}>
          <Executive />
        </MemoryRouter>
      </MantineProvider>
    </QueryClientProvider>,
  );
}

describe("Executive route", () => {
  beforeEach(() => {
    useExecutiveFilers.mockReset();
    useExecutiveFilings.mockReset();
    useExecutiveHoldings.mockReset();
    useExecutiveTransactions.mockReset();
    loadedMocks();
  });

  it("renders the header card with filer info and a link to the source filing", async () => {
    renderExecutive();
    await waitFor(() => {
      expect(screen.getByTestId("executive-page")).toBeInTheDocument();
    });
    const header = screen.getByTestId("executive-header");
    expect(within(header).getByText("Donald J. Trump")).toBeInTheDocument();
    // formatDate turns 2024-08-15 into 15/08/2024
    expect(within(header).getByText("15/08/2024")).toBeInTheDocument();
    // Header shows filing_count (3) and transaction_count (12). formatNumber
    // pads with two decimals by default, so "3" appears inside "3 filings".
    expect(within(header).getByText(/3 filings/)).toBeInTheDocument();
    expect(within(header).getByText(/12 transactions/)).toBeInTheDocument();
    const link = screen.getByTestId("executive-source-link");
    expect(link).toHaveAttribute("href", "https://oge.example/2024-q2.pdf");
  });

  it("renders the transactions table with the mock row data", async () => {
    renderExecutive();
    await waitFor(() => {
      expect(screen.getByTestId("executive-tx-table")).toBeInTheDocument();
    });
    const rows = screen.getAllByTestId("executive-tx-row");
    expect(rows).toHaveLength(1);
    const table = screen.getByTestId("executive-tx-table");
    expect(within(table).getByText("Apple Inc Common Stock")).toBeInTheDocument();
    // "Buy" also appears in the MultiSelect dropdown options; assert inside the table.
    expect(within(table).getByText("Buy")).toBeInTheDocument();
    expect(within(table).getByText("AAPL")).toBeInTheDocument();
    expect(within(table).getByText("approved")).toBeInTheDocument();
  });

  it("exposes the lookback and transaction-type filters", async () => {
    renderExecutive();
    await waitFor(() => {
      expect(screen.getByTestId("executive-lookback")).toBeInTheDocument();
    });
    expect(screen.getByTestId("executive-lookback")).toBeInTheDocument();
    expect(screen.getByTestId("executive-type-filter")).toBeInTheDocument();
    expect(screen.getByTestId("executive-filing-filter")).toBeInTheDocument();
    expect(screen.getByTestId("executive-owner-filter")).toBeInTheDocument();
  });

  it("renders an empty state when the API returns no filers and no filings", async () => {
    emptyMocks();
    renderExecutive();
    await waitFor(() => {
      expect(screen.getByTestId("executive-empty")).toBeInTheDocument();
    });
    expect(screen.getByTestId("executive-empty")).toHaveTextContent(
      /No Executive filings ingested yet/,
    );
    expect(screen.queryByTestId("executive-tx-table")).not.toBeInTheDocument();
  });
});