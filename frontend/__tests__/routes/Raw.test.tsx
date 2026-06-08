import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";

import { FilterProvider } from "@/components/FilterContext";
import { Raw } from "@/routes/Raw";

const useRawTransactions = vi.fn();
const useHealth = vi.fn();

vi.mock("@/api/raw", () => ({
  useRawTransactions: (...args: unknown[]) => useRawTransactions(...args),
  rawExportCsvUrl: () => "/api/raw/export.csv?lookback=1&sort=transaction_date&order=desc&page=1&page_size=50",
}));

vi.mock("@/api/health", () => ({
  useHealth: () => useHealth(),
}));

const sampleData = {
  ready: true,
  total: 2,
  page: 1,
  page_size: 50,
  total_pages: 1,
  sort: { column: "transaction_date", order: "desc" },
  rows: [
    { member: "Alice", ticker: "AAPL", transaction_date: "2024-06-01", amount_low: 1000, amount_high: 15000 },
    { member: "Bob", ticker: "MSFT", transaction_date: "2024-05-01", amount_low: 500, amount_high: 5000 },
  ],
  columns: [
    { key: "member", label: "Member", type: "text", sortable: true },
    { key: "ticker", label: "Ticker", type: "text", sortable: true },
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
    useHealth.mockReturnValue({ data: { polygon_cache_rows: 0 } });
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

  it("shows polygon alert when toggle is on and cache empty", async () => {
    useRawTransactions.mockReturnValue({ data: sampleData, isLoading: false, isError: false });
    renderRaw();
    const user = userEvent.setup();
    await user.click(screen.getByTestId("raw-polygon-toggle"));
    expect(screen.getByTestId("raw-polygon-alert")).toBeInTheDocument();
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
