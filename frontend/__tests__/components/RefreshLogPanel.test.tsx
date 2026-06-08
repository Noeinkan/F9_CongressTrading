import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { RefreshLogPanel, downloadRefreshLog } from "@/components/RefreshLogPanel";

describe("RefreshLogPanel", () => {
  it("shows waiting placeholder when there are no lines", () => {
    render(
      <MantineProvider>
        <RefreshLogPanel lines={[]} startedAt={null} isLive />
      </MantineProvider>,
    );
    expect(screen.getByText("Waiting for output…")).toBeInTheDocument();
    expect(screen.getByTestId("sidebar-refresh-log-download")).toBeDisabled();
  });

  it("renders log lines and download button", () => {
    render(
      <MantineProvider>
        <RefreshLogPanel
          lines={["Scarico 2024 da https://example.com", "Trovati 120 PDF"]}
          startedAt="2026-06-08T21:00:00+00:00"
          isLive
        />
      </MantineProvider>,
    );
    expect(screen.getByText("Live log")).toBeInTheDocument();
    expect(screen.getByText("Scarico 2024 da https://example.com")).toBeInTheDocument();
    expect(screen.getByTestId("sidebar-refresh-log-download")).toBeEnabled();
  });

  it("downloadRefreshLog creates a text file link", async () => {
    const user = userEvent.setup();
    const click = vi.fn();
    const createObjectURL = vi.fn(() => "blob:test");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", { createObjectURL, revokeObjectURL });

    const originalCreateElement = document.createElement.bind(document);
    vi.spyOn(document, "createElement").mockImplementation((tagName: string) => {
      if (tagName === "a") {
        return { click, download: "", href: "" } as HTMLAnchorElement;
      }
      return originalCreateElement(tagName);
    });

    render(
      <MantineProvider>
        <RefreshLogPanel lines={["line one", "line two"]} startedAt="2026-06-08T21:00:00+00:00" isLive={false} />
      </MantineProvider>,
    );

    await user.click(screen.getByTestId("sidebar-refresh-log-download"));

    expect(createObjectURL).toHaveBeenCalled();
    expect(click).toHaveBeenCalled();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:test");

    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("downloadRefreshLog handles empty lines", () => {
    const click = vi.fn();
    vi.stubGlobal("URL", {
      createObjectURL: vi.fn(() => "blob:empty"),
      revokeObjectURL: vi.fn(),
    });
    const anchor = { click, download: "", href: "" } as HTMLAnchorElement;
    vi.spyOn(document, "createElement").mockReturnValue(anchor);

    downloadRefreshLog([], null);

    expect(click).toHaveBeenCalled();
    vi.unstubAllGlobals();
  });
});
