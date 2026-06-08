import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PillStrip } from "@/components/PillStrip";

describe("PillStrip", () => {
  it("renders badges with labels and counts", () => {
    render(
      <MantineProvider>
        <PillStrip
          testId="pill-strip"
          items={[
            { label: "House", count: 42, color: "teal" },
            { label: "Senate", count: 18, color: "teal" },
          ]}
        />
      </MantineProvider>,
    );
    expect(screen.getByTestId("pill-strip")).toBeInTheDocument();
    expect(screen.getByText(/House/)).toBeInTheDocument();
    expect(screen.getByText(/Senate/)).toBeInTheDocument();
  });
});
