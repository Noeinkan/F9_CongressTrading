import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ChartCard } from "@/components/ChartCard";

describe("ChartCard", () => {
  it("renders title, caption, and children", () => {
    render(
      <MantineProvider>
        <ChartCard title="Monthly activity" caption="Transactions per month" testId="chart-card">
          <div>child content</div>
        </ChartCard>
      </MantineProvider>,
    );
    expect(screen.getByTestId("chart-card")).toBeInTheDocument();
    expect(screen.getByText("Monthly activity")).toBeInTheDocument();
    expect(screen.getByText("Transactions per month")).toBeInTheDocument();
    expect(screen.getByText("child content")).toBeInTheDocument();
  });
});
