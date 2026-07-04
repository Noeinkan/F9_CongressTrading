import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ComponentProps } from "react";
import { describe, expect, it } from "vitest";

import { ChartCard } from "@/components/ChartCard";

function renderChartCard(props: ComponentProps<typeof ChartCard>) {
  return render(
    <MantineProvider>
      <ChartCard {...props} />
    </MantineProvider>,
  );
}

describe("ChartCard", () => {
  it("renders title, caption, and children", () => {
    renderChartCard({
      title: "Monthly activity",
      caption: "Transactions per month",
      testId: "chart-card",
      children: <div>child content</div>,
    });
    expect(screen.getByTestId("chart-card")).toBeInTheDocument();
    expect(screen.getByText("Monthly activity")).toBeInTheDocument();
    expect(screen.getByText("Transactions per month")).toBeInTheDocument();
    expect(screen.getByText("child content")).toBeInTheDocument();
  });

  it("renders collapsible panels expanded by default", () => {
    renderChartCard({
      collapsible: true,
      title: "Latest activity",
      testId: "chart-card",
      children: <div>child content</div>,
    });
    const toggle = screen.getByRole("button", { name: "Latest activity" });
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("child content")).toBeVisible();
  });

  it("collapses panel content when header is clicked", async () => {
    const user = userEvent.setup();
    renderChartCard({
      collapsible: true,
      title: "Latest activity",
      testId: "chart-card",
      children: <div>child content</div>,
    });
    const toggle = screen.getByRole("button", { name: "Latest activity" });
    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByText("child content")).not.toBeVisible();
  });

  it("does not render collapse affordance when collapsible is false", () => {
    renderChartCard({
      title: "Transactions",
      testId: "chart-card",
      children: <div>child content</div>,
    });
    expect(screen.queryByRole("button", { name: "Transactions" })).not.toBeInTheDocument();
    expect(screen.getByText("child content")).toBeInTheDocument();
  });

  it("starts collapsed when defaultCollapsed is true", () => {
    renderChartCard({
      collapsible: true,
      defaultCollapsed: true,
      title: "Latest activity",
      testId: "chart-card",
      children: <div>child content</div>,
    });
    const toggle = screen.getByRole("button", { name: "Latest activity" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByText("child content")).not.toBeVisible();
  });
});
