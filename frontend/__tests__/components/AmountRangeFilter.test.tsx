import { MantineProvider } from "@mantine/core";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { AmountRangeFilter } from "@/components/AmountRangeFilter";

function wrap(ui: React.ReactNode) {
  return render(<MantineProvider>{ui}</MantineProvider>);
}

describe("AmountRangeFilter", () => {
  const rows = [
    { amount_low: 1_000, amount_high: 5_000, amount_range_raw: "$1K – $5K" },
    { amount_low: 8_000, amount_high: 12_000, amount_range_raw: "$1K – $15K" },
    { amount_low: 20_000, amount_high: 40_000, amount_range_raw: "$15K – $50K" },
    { amount_low: 600_000, amount_high: 900_000, amount_range_raw: "$500K – $1M" },
    { amount_low: 2_000_000, amount_high: 4_000_000, amount_range_raw: "$1M – $5M" },
  ];

  it("shows the total count and per-bucket counts when collapsed", () => {
    wrap(<AmountRangeFilter rows={rows} value={null} onChange={() => {}} />);
    // Header badge reads "All 5".
    expect(screen.getByText(/All 5/)).toBeInTheDocument();
    // Open the accordion panel to inspect the items.
    const trigger = screen.getByRole("button", { name: /Filter by disclosed amount range/i });
    trigger.click();
    const panel = screen.getByTestId("amount-range-filter-items");
    expect(within(panel).getByTestId("amount-range-filter-item-all")).toHaveTextContent("5");
    expect(within(panel).getByTestId("amount-range-filter-item-1k-15k")).toHaveTextContent("2");
    expect(within(panel).getByTestId("amount-range-filter-item-15k-50k")).toHaveTextContent("1");
    expect(within(panel).getByTestId("amount-range-filter-item-500k-1m")).toHaveTextContent("1");
    expect(within(panel).getByTestId("amount-range-filter-item-1m-5m")).toHaveTextContent("1");
  });

  it("emits the clicked bucket key", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    wrap(<AmountRangeFilter rows={rows} value={null} onChange={onChange} />);
    // Open the panel.
    await user.click(screen.getByRole("button", { name: /Filter by disclosed amount range/i }));
    await user.click(screen.getByTestId("amount-range-filter-item-500k-1m"));
    expect(onChange).toHaveBeenLastCalledWith("500k-1m");
  });

  it("emits null when 'All ranges' is clicked", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    wrap(<AmountRangeFilter rows={rows} value="500k-1m" onChange={onChange} />);
    await user.click(screen.getByRole("button", { name: /Filter by disclosed amount range/i }));
    await user.click(screen.getByTestId("amount-range-filter-item-all"));
    expect(onChange).toHaveBeenCalledWith(null);
  });

  it("shows a Clear filter button when a bucket is selected", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    wrap(<AmountRangeFilter rows={rows} value="1k-15k" onChange={onChange} />);
    await user.click(screen.getByTestId("amount-range-filter-reset"));
    expect(onChange).toHaveBeenCalledWith(null);
  });
});