import { MantineProvider } from "@mantine/core";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DemoEntry } from "@/routes/DemoEntry";

const navigateMock = vi.fn();
vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => navigateMock };
});

const useDemoStatusMock = vi.fn();
vi.mock("@/api/demo", () => ({
  useDemoStatus: () => useDemoStatusMock(),
}));

function renderEntry() {
  return render(
    <MantineProvider>
      <MemoryRouter initialEntries={["/demo"]}>
        <DemoEntry />
      </MemoryRouter>
    </MantineProvider>,
  );
}

describe("DemoEntry", () => {
  beforeEach(() => {
    navigateMock.mockReset();
  });

  it("shows a loader while the demo status is still in flight", () => {
    useDemoStatusMock.mockReturnValue({ data: undefined });
    renderEntry();
    expect(screen.getByTestId("demo-entry-loading")).toBeInTheDocument();
    expect(navigateMock).not.toHaveBeenCalled();
  });

  it("sends a signed-out visitor to the email sign-in form", async () => {
    useDemoStatusMock.mockReturnValue({
      data: { enabled: true, access: { gate: true, status: "signed_out" } },
    });
    renderEntry();
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith("/access", { replace: true }));
  });

  it("sends an already-active visitor straight to the dashboard", async () => {
    useDemoStatusMock.mockReturnValue({
      data: { enabled: true, access: { gate: true, status: "active" } },
    });
    renderEntry();
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith("/", { replace: true }));
  });

  it("sends an ended visitor to the ended page", async () => {
    useDemoStatusMock.mockReturnValue({
      data: { enabled: true, access: { gate: true, status: "ended" } },
    });
    renderEntry();
    await waitFor(() =>
      expect(navigateMock).toHaveBeenCalledWith("/access/ended", { replace: true }),
    );
  });

  it("sends a revoked visitor to the ended page", async () => {
    useDemoStatusMock.mockReturnValue({
      data: { enabled: true, access: { gate: true, status: "revoked" } },
    });
    renderEntry();
    await waitFor(() =>
      expect(navigateMock).toHaveBeenCalledWith("/access/ended", { replace: true }),
    );
  });

  it("skips straight to the dashboard when the gate itself is off", async () => {
    useDemoStatusMock.mockReturnValue({
      data: { enabled: true, access: { gate: false } },
    });
    renderEntry();
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith("/", { replace: true }));
  });

  it("falls back to the real sign-in when this deployment has no demo", async () => {
    useDemoStatusMock.mockReturnValue({ data: { enabled: false } });
    renderEntry();
    await waitFor(() =>
      expect(screen.getByText(/not the public demo/i)).toBeInTheDocument(),
    );
    expect(navigateMock).not.toHaveBeenCalled();
  });
});
