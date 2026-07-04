import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { formatDuration, formatEta } from "@/api/refresh";
import { RefreshProgressPanel } from "@/components/RefreshProgressPanel";

const baseStatus = {
  status: "running" as const,
  started_at: "2026-06-08T21:00:00+00:00",
  finished_at: null,
  current_step: "ingest-house",
  progress: 42,
  phase_label: "Parsing House PTR PDFs",
  phase_index: 1,
  phase_total: 5,
  sub_progress: 30,
  sub_done: 3,
  sub_total: 10,
  sub_unit: "PDFs",
  eta_seconds: 98,
  step_started_at: "2026-06-08T21:00:10+00:00",
  log_tail: ["House FD 2024: TXT rows=2215 PTR-rows=450"],
  log_lines: ["House FD 2024: TXT rows=2215 PTR-rows=450", "ERROR: something failed"],
  result: {},
};

describe("formatEta", () => {
  it("formats null as placeholder", () => {
    expect(formatEta(null)).toBe("ETA —");
  });

  it("formats seconds into a left label", () => {
    expect(formatEta(134)).toBe("ETA ~2m 14s left");
  });
});

describe("formatDuration", () => {
  it("formats minutes and seconds", () => {
    expect(formatDuration(134)).toBe("2m 14s");
  });
});

describe("RefreshProgressPanel", () => {
  it("renders sub-progress and ETA while live", () => {
    render(
      <MantineProvider>
        <RefreshProgressPanel status={baseStatus} isLive />
      </MantineProvider>,
    );

    expect(screen.getByText(/Parsing House PTR PDFs: 3 of 10 PDFs/)).toBeInTheDocument();
    expect(screen.getByTestId("sidebar-refresh-eta")).toHaveTextContent("ETA ~1m 38s left");
    expect(screen.getByTestId("sidebar-refresh-elapsed")).toBeInTheDocument();
  });

  it("highlights the active phase in the expanded stepper", () => {
    render(
      <MantineProvider>
        <RefreshProgressPanel status={baseStatus} isLive variant="expanded" showStepper />
      </MantineProvider>,
    );

    expect(screen.getByTestId("sidebar-refresh-phase-1")).toBeInTheDocument();
    expect(screen.getByTestId("sidebar-refresh-phase-step-1")).toBeInTheDocument();
  });

  it("color-codes error log lines", () => {
    render(
      <MantineProvider>
        <RefreshProgressPanel status={baseStatus} isLive={false} />
      </MantineProvider>,
    );

    expect(screen.getByText("ERROR: something failed")).toHaveAttribute("class");
  });

  it("shows terminal footer in expanded mode", () => {
    render(
      <MantineProvider>
        <RefreshProgressPanel
          status={{ ...baseStatus, status: "succeeded", progress: 100 }}
          isLive={false}
          variant="expanded"
          showTerminalFooter
          resultSummary={{ rowsPtr: 12, rowsTotal: 99, senate: { pdfs: 0 } }}
        />
      </MantineProvider>,
    );

    expect(screen.getByTestId("sidebar-refresh-success")).toHaveTextContent("Refresh completed");
    expect(screen.getByText(/12 PTR rows seen/)).toBeInTheDocument();
  });
});
