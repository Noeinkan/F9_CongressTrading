import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DemoBanner } from "@/components/DemoBanner";

const useDemoStatusMock = vi.fn();
vi.mock("@/api/demo", () => ({
  useDemoStatus: () => useDemoStatusMock(),
}));

function renderBanner() {
  return render(
    <MantineProvider>
      <DemoBanner />
    </MantineProvider>,
  );
}

describe("DemoBanner", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    useDemoStatusMock.mockReset();
  });

  it("renders nothing on a normal deployment", () => {
    useDemoStatusMock.mockReturnValue({ data: { enabled: false } });
    renderBanner();
    expect(screen.queryByTestId("demo-banner")).not.toBeInTheDocument();
  });

  it("renders nothing while the status is still loading", () => {
    useDemoStatusMock.mockReturnValue({ data: undefined });
    renderBanner();
    expect(screen.queryByTestId("demo-banner")).not.toBeInTheDocument();
  });

  it("states the limits and the snapshot date when the demo is live", () => {
    useDemoStatusMock.mockReturnValue({
      data: {
        enabled: true,
        readOnly: true,
        notice: "You are in the public demo.",
        snapshotLabel: "Snapshot: 12 September 2026",
        sourceUrl: "https://noeinsolutions.com/builds.html",
      },
    });
    renderBanner();
    expect(screen.getByTestId("demo-banner")).toBeInTheDocument();
    expect(screen.getByText("You are in the public demo.")).toBeInTheDocument();
    expect(screen.getByTestId("demo-banner-snapshot")).toHaveTextContent(
      "Snapshot: 12 September 2026",
    );
    expect(screen.getByText(/does not refresh/i)).toBeInTheDocument();
  });

  it("stays dismissed for the rest of the tab session", async () => {
    useDemoStatusMock.mockReturnValue({
      data: { enabled: true, notice: "Demo.", snapshotLabel: "Snapshot: 12 September 2026" },
    });
    const { unmount } = renderBanner();
    await userEvent.click(screen.getByLabelText(/dismiss the demo notice/i));
    expect(screen.queryByTestId("demo-banner")).not.toBeInTheDocument();

    unmount();
    renderBanner();
    expect(screen.queryByTestId("demo-banner")).not.toBeInTheDocument();
  });
});
