import { MantineProvider } from "@mantine/core";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { FilterProvider, useFilters } from "@/components/FilterContext";
import { SidebarFilters } from "@/components/SidebarFilters";

function Probe() {
  const { lookback, quarters } = useFilters();
  return (
    <div>
      <span data-testid="probe-lookback">{lookback}</span>
      <span data-testid="probe-quarters">{quarters.join(",")}</span>
    </div>
  );
}

function renderSidebar(initial?: { lookback?: number; quarters?: ("1" | "2" | "3" | "4")[] }) {
  return render(
    <MantineProvider>
      <MemoryRouter>
        <FilterProvider
          initialLookback={initial?.lookback}
          initialQuarters={initial?.quarters}
        >
          <SidebarFilters />
          <Probe />
        </FilterProvider>
      </MemoryRouter>
    </MantineProvider>,
  );
}

describe("SidebarFilters", () => {
  it("renders the sidebar shell", () => {
    renderSidebar();
    expect(screen.getByTestId("sidebar-filters")).toBeInTheDocument();
    expect(screen.getByTestId("sidebar-lookback")).toBeInTheDocument();
    expect(screen.getByTestId("sidebar-quarters")).toBeInTheDocument();
    expect(screen.getByTestId("sidebar-reset")).toBeInTheDocument();
  });

  it("shows all four quarter buttons", () => {
    renderSidebar();
    const quarters = screen.getByTestId("sidebar-quarters");
    for (const q of ["1", "2", "3", "4"]) {
      expect(within(quarters).getByTestId(`sidebar-quarter-${q}`)).toBeInTheDocument();
    }
  });

  it("reset returns lookback and quarters to defaults", async () => {
    const user = userEvent.setup();
    renderSidebar({ lookback: 5, quarters: ["1"] });
    expect(screen.getByTestId("probe-lookback")).toHaveTextContent("5");
    expect(screen.getByTestId("probe-quarters")).toHaveTextContent("1");

    await user.click(screen.getByTestId("sidebar-reset"));
    expect(screen.getByTestId("probe-lookback")).toHaveTextContent("1");
    expect(screen.getByTestId("probe-quarters")).toHaveTextContent("1,2,3,4");
  });

  it("toggling a quarter updates the context", async () => {
    const user = userEvent.setup();
    renderSidebar({ quarters: ["1", "2", "3", "4"] });
    await user.click(screen.getByTestId("sidebar-quarter-2"));
    expect(screen.getByTestId("probe-quarters")).toHaveTextContent("1,3,4");
  });

  it("toggling the last remaining quarter is a no-op", async () => {
    const user = userEvent.setup();
    renderSidebar({ quarters: ["1"] });
    await user.click(screen.getByTestId("sidebar-quarter-1"));
    expect(screen.getByTestId("probe-quarters")).toHaveTextContent("1");
  });
});
