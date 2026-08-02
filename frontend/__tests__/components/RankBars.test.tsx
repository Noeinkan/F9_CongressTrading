import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { RankBars } from "@/components/RankBars";

const mockEcharts = vi.fn((_props: Record<string, unknown>) => (
  <div data-testid="rank-bars-chart" />
));

vi.mock("echarts-for-react", () => ({
  default: (props: Record<string, unknown>) => mockEcharts(props),
}));

function renderRankBars(ui: React.ReactElement) {
  return render(
    <MemoryRouter>
      <MantineProvider>{ui}</MantineProvider>
    </MemoryRouter>,
  );
}

describe("RankBars", () => {
  it("renders chart for non-empty rows", () => {
    renderRankBars(
      <RankBars
        testId="rank-bars"
        rows={[
          { label: "Alice", value: 10 },
          { label: "Bob", value: 5 },
        ]}
      />,
    );
    expect(screen.getByTestId("rank-bars")).toBeInTheDocument();
  });

  it("wires onEvents.click when linkKind is set", () => {
    mockEcharts.mockClear();
    renderRankBars(
      <RankBars
        testId="rank-bars"
        linkKind="member"
        rows={[
          { label: "Alice", value: 10 },
          { label: "Bob", value: 5 },
        ]}
      />,
    );
    const lastCall = mockEcharts.mock.calls.at(-1)?.[0] as {
      onEvents?: { click?: unknown };
      option?: { yAxis?: { triggerEvent?: boolean } };
    };
    expect(typeof lastCall.onEvents?.click).toBe("function");
    expect(lastCall.option?.yAxis?.triggerEvent).toBe(true);
  });

  it("does not wire onEvents when linkKind is omitted", () => {
    mockEcharts.mockClear();
    renderRankBars(
      <RankBars
        testId="rank-bars"
        rows={[{ label: "Filer", value: 3 }]}
      />,
    );
    const lastCall = mockEcharts.mock.calls.at(-1)?.[0] as {
      onEvents?: unknown;
      option?: { yAxis?: { triggerEvent?: boolean } };
    };
    expect(lastCall.onEvents).toBeUndefined();
    expect(lastCall.option?.yAxis?.triggerEvent).toBe(false);
  });
});
