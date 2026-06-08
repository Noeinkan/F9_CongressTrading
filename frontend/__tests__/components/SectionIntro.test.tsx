import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SectionIntro } from "@/components/SectionIntro";

describe("SectionIntro", () => {
  it("renders kicker, title, and copy", () => {
    render(
      <MantineProvider>
        <SectionIntro kicker="Overview" title="Where activity is clustering" copy="Test copy" />
      </MantineProvider>,
    );
    expect(screen.getByTestId("section-intro")).toBeInTheDocument();
    expect(screen.getByText("Overview")).toBeInTheDocument();
    expect(screen.getByText("Where activity is clustering")).toBeInTheDocument();
    expect(screen.getByText("Test copy")).toBeInTheDocument();
  });
});
