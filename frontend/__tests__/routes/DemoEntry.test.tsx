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

const useSessionProbeMock = vi.fn();
vi.mock("@/api/auth", () => ({
  useSessionProbe: () => useSessionProbeMock(),
}));

const useDemoStatusMock = vi.fn();
const signInMock = vi.fn();
vi.mock("@/api/demo", () => ({
  useDemoStatus: () => useDemoStatusMock(),
  useDemoSignIn: () => ({ mutateAsync: signInMock }),
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
    signInMock.mockReset();
    useSessionProbeMock.mockReturnValue({
      data: { authenticated: false, auth_required: true, user: null },
    });
    useDemoStatusMock.mockReturnValue({ data: { enabled: true } });
  });

  it("signs the visitor in and lands them on the dashboard", async () => {
    signInMock.mockResolvedValue({ user: "demo", demo: true, snapshotDate: "2026-09-12" });
    renderEntry();

    expect(screen.getByTestId("demo-entry-loading")).toBeInTheDocument();
    await waitFor(() => expect(signInMock).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(navigateMock).toHaveBeenCalledWith("/", { replace: true }),
    );
  });

  it("never mints twice, even across re-renders", async () => {
    signInMock.mockResolvedValue({ user: "demo", demo: true, snapshotDate: "2026-09-12" });
    const { rerender } = renderEntry();
    await waitFor(() => expect(signInMock).toHaveBeenCalledTimes(1));
    rerender(
      <MantineProvider>
        <MemoryRouter initialEntries={["/demo"]}>
          <DemoEntry />
        </MemoryRouter>
      </MantineProvider>,
    );
    expect(signInMock).toHaveBeenCalledTimes(1);
  });

  it("falls back to the real sign-in when this deployment has no demo", async () => {
    useDemoStatusMock.mockReturnValue({ data: { enabled: false } });
    renderEntry();
    await waitFor(() =>
      expect(screen.getByText(/not the public demo/i)).toBeInTheDocument(),
    );
    expect(signInMock).not.toHaveBeenCalled();
  });

  it("falls back when the mint call itself fails", async () => {
    signInMock.mockRejectedValue(new Error("404"));
    renderEntry();
    await waitFor(() =>
      expect(screen.getByText(/not the public demo/i)).toBeInTheDocument(),
    );
  });
});
