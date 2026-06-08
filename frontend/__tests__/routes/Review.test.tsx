import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { FilterProvider } from "@/components/FilterContext";
import { Review } from "@/routes/Review";

const useReviewSummary = vi.fn();

vi.mock("@/api/review", () => ({
  useReviewSummary: (...args: unknown[]) => useReviewSummary(...args),
}));

vi.mock("echarts-for-react", () => ({
  default: ({ "data-testid": testId }: { "data-testid"?: string }) => (
    <div data-testid={testId ?? "echarts-mock"} />
  ),
}));

const sampleData = {
  ready: true,
  review_source: "sqlite",
  kpis: {
    open_count: 5,
    total_count: 10,
    high_confidence_pct: 0.7,
    high_confidence_label: "70%",
    by_reason: [{ reason: "ticker", records: 4 }],
    by_status: [{ status: "open", records: 5 }],
    by_month: [],
  },
  rows: [
    {
      reason: "ticker",
      status: "open",
      member: "Alice",
      ticker: "AAPL",
      transaction_type: "P",
      transaction_type_label: "Buy",
      amount_range_raw: "$1K – $15K",
      confidence_score: 0.8,
      transaction_date: "2024-06-01",
      filing_date: "2024-06-15",
      asset_name_raw: "Apple Inc",
    },
  ],
  total: 1,
  limit: 40,
  offset: 0,
};

function renderReview() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MantineProvider>
        <FilterProvider>
          <MemoryRouter>
            <Review />
          </MemoryRouter>
        </FilterProvider>
      </MantineProvider>
    </QueryClientProvider>,
  );
}

describe("Review route", () => {
  beforeEach(() => {
    useReviewSummary.mockReset();
  });

  it("shows loading state", () => {
    useReviewSummary.mockReturnValue({ data: undefined, isLoading: true, isError: false });
    renderReview();
    expect(screen.getByTestId("page-loading")).toBeInTheDocument();
  });

  it("renders KPIs and tables when data resolves", async () => {
    useReviewSummary.mockReturnValue({ data: sampleData, isLoading: false, isError: false });
    renderReview();
    await waitFor(() => {
      expect(screen.getByTestId("review-page")).toBeInTheDocument();
    });
    expect(screen.getByTestId("kpi-tile-open")).toBeInTheDocument();
    expect(screen.getByTestId("review-by-reason")).toBeInTheDocument();
    expect(screen.getByTestId("review-summary-table")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Alice" })).toHaveAttribute(
      "href",
      "/members?member=Alice",
    );
  });
});
