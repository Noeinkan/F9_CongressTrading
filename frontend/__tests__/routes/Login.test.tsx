import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/api/client";
import { Login } from "@/routes/Login";

const mutateAsync = vi.fn();
const useLoginMock = vi.fn();
const useSessionProbeMock = vi.fn();

vi.mock("@/api/auth", () => ({
  useLogin: () => useLoginMock(),
  useSessionProbe: () => useSessionProbeMock(),
}));

function renderLogin(initialEntries: string[] = ["/login"]) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <MantineProvider>
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={initialEntries}>
          <Login />
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>,
  );
}

describe("Login", () => {
  beforeEach(() => {
    mutateAsync.mockReset();
    useLoginMock.mockReturnValue({
      mutateAsync,
      isPending: false,
    });
    useSessionProbeMock.mockReturnValue({
      isLoading: false,
      isError: false,
      data: { authenticated: false, auth_required: true, user: null },
      refetch: vi.fn(),
    });
  });

  it("renders the sign-in form", () => {
    renderLogin();
    expect(screen.getByRole("heading", { name: /sign in/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/username/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
  });

  it("posts credentials on submit", async () => {
    const user = userEvent.setup();
    mutateAsync.mockResolvedValue({ user: "admin", auth_required: true });
    renderLogin();

    await user.type(screen.getByLabelText(/username/i), "admin");
    await user.type(screen.getByLabelText(/password/i), "secret");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(mutateAsync).toHaveBeenCalledWith({
        username: "admin",
        password: "secret",
      });
    });
  });

  it("shows a 401-specific error and clears the password on bad credentials", async () => {
    const user = userEvent.setup();
    mutateAsync.mockRejectedValue(
      new ApiError(401, { detail: "Invalid" }, "Unauthorized"),
    );
    renderLogin();

    const username = screen.getByLabelText(/username/i) as HTMLInputElement;
    const password = screen.getByLabelText(/password/i) as HTMLInputElement;
    await user.type(username, "admin");
    await user.type(password, "wrong");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(screen.getByTestId("login-error")).toHaveTextContent(
        /invalid username or password/i,
      );
    });
    expect(password.value).toBe("");
    expect(username.value).toBe("admin");
  });

  it("shows a generic error and keeps the password on a non-401 failure", async () => {
    const user = userEvent.setup();
    mutateAsync.mockRejectedValue(new ApiError(500, { detail: "boom" }));
    renderLogin();

    const password = screen.getByLabelText(/password/i) as HTMLInputElement;
    await user.type(screen.getByLabelText(/username/i), "admin");
    await user.type(password, "secret");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(screen.getByTestId("login-error")).toHaveTextContent(/login failed/i);
    });
    expect(password.value).toBe("secret");
  });

  it("disables the submit button while the login mutation is pending", () => {
    useLoginMock.mockReturnValue({ mutateAsync, isPending: true });
    renderLogin();
    expect(screen.getByRole("button", { name: /sign in/i })).toBeDisabled();
  });
});
