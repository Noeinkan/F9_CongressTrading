import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { MiniSparkline } from "@/components/MiniSparkline";

vi.mock("echarts-for-react", () => ({
  default: () => <div data-testid="echarts-mock" />,
}));

describe("MiniSparkline", () => {
  it("renders chart when points exist", () => {
    render(
      <MantineProvider>
        <MiniSparkline points={[{ month: "2024-01", value: 3 }]} />
      </MantineProvider>,
    );
    expect(screen.getByTestId("mini-sparkline")).toBeInTheDocument();
  });

  it("renders nothing when points are empty", () => {
    const { container } = render(
      <MantineProvider>
        <MiniSparkline points={[]} />
      </MantineProvider>,
    );
    expect(container.querySelector("[data-testid='mini-sparkline']")).toBeNull();
  });
});
