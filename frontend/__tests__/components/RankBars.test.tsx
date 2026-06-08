import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { RankBars } from "@/components/RankBars";

vi.mock("echarts-for-react", () => ({
  default: () => <div data-testid="rank-bars-chart" />,
}));

describe("RankBars", () => {
  it("renders chart for non-empty rows", () => {
    render(
      <MantineProvider>
        <RankBars
          testId="rank-bars"
          rows={[
            { label: "Alice", value: 10 },
            { label: "Bob", value: 5 },
          ]}
        />
      </MantineProvider>,
    );
    expect(screen.getByTestId("rank-bars")).toBeInTheDocument();
  });
});
