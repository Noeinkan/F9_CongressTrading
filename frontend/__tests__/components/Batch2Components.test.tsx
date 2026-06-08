import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { BarChart } from "@/components/BarChart";
import { KpiTileSimple } from "@/components/KpiTileSimple";
import { PriceOverlayChart } from "@/components/PriceOverlayChart";

vi.mock("echarts-for-react", () => ({
  default: ({ "data-testid": testId }: { "data-testid"?: string }) => (
    <div data-testid={testId ?? "echarts-mock"} />
  ),
}));

describe("BarChart", () => {
  it("renders chart when rows exist", () => {
    render(
      <MantineProvider>
        <BarChart testId="test-bar" rows={[{ label: "A", value: 3 }]} />
      </MantineProvider>,
    );
    expect(screen.getByTestId("test-bar")).toBeInTheDocument();
    expect(screen.getByTestId("bar-chart")).toBeInTheDocument();
  });
});

describe("KpiTileSimple", () => {
  it("renders label and value", () => {
    render(
      <MantineProvider>
        <KpiTileSimple kpi={{ key: "x", label: "Trades", value: 42 }} />
      </MantineProvider>,
    );
    expect(screen.getByTestId("kpi-tile-x")).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();
  });
});

describe("PriceOverlayChart", () => {
  it("renders when bars provided", () => {
    render(
      <MantineProvider>
        <PriceOverlayChart
          bars={[{ date: "2024-01-01", close: 100 }]}
          trades={[]}
        />
      </MantineProvider>,
    );
    expect(screen.getByTestId("price-overlay-chart")).toBeInTheDocument();
  });
});
