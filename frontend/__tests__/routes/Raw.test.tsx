import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";

import { FilterProvider } from "@/components/FilterContext";
import { Raw } from "@/routes/Raw";

const useRawTransactions = vi.fn();

vi.mock("@/api/raw", () => ({
  useRawTransactions: (...args: unknown[]) => useRawTransactions(...args),
  rawExportCsvUrl: () => "/api/raw/export.csv?lookback=1&sort=transaction_date&order=desc&page=1&page_size=50",
}));

const sampleData = {
  ready: true,
  total: 2,
  page: 1,
  page_size: 50,
  total_pages: 1,
  sort: { column: "transaction_date", order: "desc" },
  rows: [
    {
      member: "Alice",
      ticker: "AAPL",
      transaction_date: "2024-06-01",
      amount_low: 1000,
      amount_high: 15000,
      transaction_type_label: "Buy",
      amount_range_raw: "$1K – $15K",
    },
    {
      member: "Bob",
      ticker: "MSFT",
      transaction_date: "2024-05-01",
      amount_low: 500,
      amount_high: 5000,
      transaction_type_label: "Sell",
      amount_range_raw: "$1K – $15K",
    },
  ],
  columns: [
    { key: "member", label: "Member", type: "text", sortable: true },
    { key: "ticker", label: "Ticker", type: "text", sortable: true },
    { key: "transaction_type_label", label: "Type", type: "text", sortable: true },
    { key: "transaction_date", label: "Transaction date", type: "date", sortable: true },
    { key: "amount_high", label: "Amount high", type: "currency", sortable: true },
  ],
  source: "sqlite",
};

function renderRaw(initialEntries = ["/raw"]) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MantineProvider>
        <FilterProvider>
          <MemoryRouter initialEntries={initialEntries}>
            <Raw />
          </MemoryRouter>
        </FilterProvider>
      </MantineProvider>
    </QueryClientProvider>,
  );
}

describe("Raw route", () => {
  beforeEach(() => {
    useRawTransactions.mockReset();
  });

  it("renders table rows from API data", async () => {
    useRawTransactions.mockReturnValue({ data: sampleData, isLoading: false, isError: false });
    renderRaw();
    await waitFor(() => {
      expect(screen.getByTestId("raw-page")).toBeInTheDocument();
    });
    expect(screen.getAllByTestId("raw-row")).toHaveLength(2);
    expect(screen.getByText("Alice")).toBeInTheDocument();
  });

  it("applies direction badges and row tint from transaction_type_label", async () => {
    useRawTransactions.mockReturnValue({ data: sampleData, isLoading: false, isError: false });
    renderRaw();
    await waitFor(() => {
      expect(screen.getAllByTestId("raw-row")).toHaveLength(2);
    });
    const rows = screen.getAllByTestId("raw-row");
    expect(rows[0]).toHaveAttribute("data-direction", "buy");
    expect(rows[1]).toHaveAttribute("data-direction", "sell");
  });

  it("points download button at export URL", async () => {
    useRawTransactions.mockReturnValue({ data: sampleData, isLoading: false, isError: false });
    renderRaw();
    await waitFor(() => {
      expect(screen.getByTestId("raw-download")).toBeInTheDocument();
    });
    expect(screen.getByTestId("raw-download")).toHaveAttribute(
      "href",
      "/api/raw/export.csv?lookback=1&sort=transaction_date&order=desc&page=1&page_size=50",
    );
  });

  it("sort header click updates sort params via rerender", async () => {
    useRawTransactions.mockReturnValue({ data: sampleData, isLoading: false, isError: false });
    renderRaw(["/raw?sort=transaction_date&order=desc"]);
    const user = userEvent.setup();
    await user.click(screen.getByTestId("raw-sort-member"));
    await waitFor(() => {
      const calls = useRawTransactions.mock.calls;
      const lastParams = calls[calls.length - 1]?.[0];
      expect(lastParams?.sort).toBe("member");
      expect(lastParams?.order).toBe("desc");
    });
  });
});
