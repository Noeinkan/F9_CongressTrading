import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { KpiTile } from "@/components/KpiTile";

vi.mock("echarts-for-react", () => ({
  default: () => <div data-testid="echarts-inner" />,
}));

describe("KpiTile", () => {
  it("renders label, value, detail, delta, and sparkline", () => {
    render(
      <MantineProvider>
        <KpiTile
          kpi={{
            key: "transactions",
            label: "Transactions",
            value: 120,
            detail: "Rows in slice",
            sparkline: [{ month: "2024-01", value: 10 }],
            delta: { value: 2, percent: false, label: "+2 vs prior month" },
          }}
        />
      </MantineProvider>,
    );
    expect(screen.getByTestId("kpi-tile-transactions")).toBeInTheDocument();
    expect(screen.getByText("Transactions")).toBeInTheDocument();
    expect(screen.getByText("120")).toBeInTheDocument();
    expect(screen.getByText("Rows in slice")).toBeInTheDocument();
    expect(screen.getByTestId("kpi-delta")).toHaveTextContent("+2 vs prior month");
    expect(screen.getByTestId("mini-sparkline")).toBeInTheDocument();
  });
});
