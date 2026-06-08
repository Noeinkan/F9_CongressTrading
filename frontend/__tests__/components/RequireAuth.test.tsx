import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { RequireAuth } from "@/components/RequireAuth";

const useSessionProbeMock = vi.fn();
vi.mock("@/api/auth", () => ({
  useSessionProbe: () => useSessionProbeMock(),
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
});
