import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { RequireAuth } from "@/components/RequireAuth";

const useSessionProbeMock = vi.fn();
vi.mock("@/api/auth", () => ({
  useSessionProbe: () => useSessionProbeMock(),
}));

const useDemoStatusMock = vi.fn();
vi.mock("@/api/demo", () => ({
  useDemoStatus: () => useDemoStatusMock(),
}));

function renderGuard(initialPath = "/") {
  return render(
    <MantineProvider>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route element={<RequireAuth />}>
            <Route path="/" element={<div data-testid="protected">protected</div>} />
          </Route>
          <Route path="/login" element={<div data-testid="login">login</div>} />
          <Route path="/access" element={<div data-testid="access">access</div>} />
          <Route path="/access/ended" element={<div data-testid="access-ended">ended</div>} />
        </Routes>
      </MemoryRouter>
    </MantineProvider>,
  );
}

describe("RequireAuth", () => {
  beforeEach(() => {
    useSessionProbeMock.mockReturnValue({
      isLoading: false,
      isError: false,
      data: { authenticated: false, auth_required: true, user: null },
      refetch: vi.fn(),
    });
    // Off-demo by default: the demo gate never applies unless a test opts in.
    useDemoStatusMock.mockReturnValue({ isLoading: false, data: { enabled: false } });
  });

  it("shows a loading state while the session probe is in flight", () => {
    useSessionProbeMock.mockReturnValue({
      isLoading: true,
      isError: false,
      data: undefined,
      refetch: vi.fn(),
    });
    renderGuard();
    expect(screen.getByText(/checking session/i)).toBeInTheDocument();
    expect(screen.queryByTestId("protected")).not.toBeInTheDocument();
  });

  it("redirects to /login when the session probe errors", () => {
    useSessionProbeMock.mockReturnValue({
      isLoading: false,
      isError: true,
      data: undefined,
      refetch: vi.fn(),
    });
    renderGuard();
    expect(screen.getByTestId("login")).toBeInTheDocument();
  });

  it("redirects to /login when auth is required and the user is not authenticated", () => {
    useSessionProbeMock.mockReturnValue({
      isLoading: false,
      isError: false,
      data: { authenticated: false, auth_required: true, user: null },
      refetch: vi.fn(),
    });
    renderGuard();
    expect(screen.getByTestId("login")).toBeInTheDocument();
  });

  it("renders the protected route when auth is not required", () => {
    useSessionProbeMock.mockReturnValue({
      isLoading: false,
      isError: false,
      data: { authenticated: false, auth_required: false, user: "anonymous" },
      refetch: vi.fn(),
    });
    renderGuard();
    expect(screen.getByTestId("protected")).toBeInTheDocument();
  });

  it("renders the protected route when the user is authenticated", () => {
    useSessionProbeMock.mockReturnValue({
      isLoading: false,
      isError: false,
      data: { authenticated: true, auth_required: true, user: "admin" },
      refetch: vi.fn(),
    });
    renderGuard();
    expect(screen.getByTestId("protected")).toBeInTheDocument();
  });

  it("shows the loader while the demo status is still loading, even if the session already resolved", () => {
    useDemoStatusMock.mockReturnValue({ isLoading: true, data: undefined });
    renderGuard();
    expect(screen.getByText(/checking session/i)).toBeInTheDocument();
    expect(screen.queryByTestId("protected")).not.toBeInTheDocument();
  });

  it("sends a signed-out demo visitor to /access with next set to the current path", () => {
    useDemoStatusMock.mockReturnValue({
      isLoading: false,
      data: { enabled: true, access: { gate: true, status: "signed_out" } },
    });
    renderGuard("/");
    expect(screen.getByTestId("access")).toBeInTheDocument();
  });

  it("sends an ended demo visitor to /access/ended", () => {
    useDemoStatusMock.mockReturnValue({
      isLoading: false,
      data: { enabled: true, access: { gate: true, status: "ended" } },
    });
    renderGuard("/");
    expect(screen.getByTestId("access-ended")).toBeInTheDocument();
  });

  it("sends a revoked demo visitor to /access/ended", () => {
    useDemoStatusMock.mockReturnValue({
      isLoading: false,
      data: { enabled: true, access: { gate: true, status: "revoked" } },
    });
    renderGuard("/");
    expect(screen.getByTestId("access-ended")).toBeInTheDocument();
  });

  it("falls through to the ordinary session logic once demo access is active", () => {
    useDemoStatusMock.mockReturnValue({
      isLoading: false,
      data: { enabled: true, access: { gate: true, status: "active" } },
    });
    useSessionProbeMock.mockReturnValue({
      isLoading: false,
      isError: false,
      data: { authenticated: true, auth_required: false, user: "demo" },
      refetch: vi.fn(),
    });
    renderGuard("/");
    expect(screen.getByTestId("protected")).toBeInTheDocument();
  });

  it("ignores the demo gate entirely when access.gate is false", () => {
    useDemoStatusMock.mockReturnValue({
      isLoading: false,
      data: { enabled: true, access: { gate: false, status: "signed_out" } },
    });
    useSessionProbeMock.mockReturnValue({
      isLoading: false,
      isError: false,
      data: { authenticated: false, auth_required: false, user: "anonymous" },
      refetch: vi.fn(),
    });
    renderGuard("/");
    expect(screen.getByTestId("protected")).toBeInTheDocument();
  });
});
