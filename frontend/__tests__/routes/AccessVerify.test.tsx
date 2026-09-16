import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/api/client";
import { AccessVerify } from "@/routes/AccessVerify";

const navigateMock = vi.fn();
vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => navigateMock };
});

const linkInfoMock = vi.fn();
const confirmMutateAsyncMock = vi.fn();
vi.mock("@/api/demo", () => ({
  demoQueryKey: ["demo", "status"],
  useDemoAccessLinkInfo: (...args: unknown[]) => linkInfoMock(...args),
  useDemoAccessLinkConfirm: () => ({ mutateAsync: confirmMutateAsyncMock, isPending: false }),
}));

function renderVerify(token = "abc123") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MantineProvider>
        <MemoryRouter initialEntries={[`/access/verify?t=${token}`]}>
          <AccessVerify />
        </MemoryRouter>
      </MantineProvider>
    </QueryClientProvider>,
  );
}

describe("AccessVerify", () => {
  beforeEach(() => {
    navigateMock.mockReset();
    linkInfoMock.mockReset();
    confirmMutateAsyncMock.mockReset();
  });

  it("looks the token up on load (a GET) without signing in", () => {
    linkInfoMock.mockReturnValue({
      data: { address: "person@example.com" },
      isLoading: false,
      isError: false,
    });
    renderVerify();
    expect(screen.getByText(/continue as person@example.com/i)).toBeInTheDocument();
    expect(confirmMutateAsyncMock).not.toHaveBeenCalled();
  });

  it("only POSTs (spends the link) when the button is clicked", async () => {
    linkInfoMock.mockReturnValue({
      data: { address: "person@example.com" },
      isLoading: false,
      isError: false,
    });
    confirmMutateAsyncMock.mockResolvedValue({
      status: "ok",
      access: { gate: true, status: "active" },
    });
    const user = userEvent.setup();
    renderVerify("abc123");
    expect(confirmMutateAsyncMock).not.toHaveBeenCalled();
    await user.click(screen.getByTestId("access-verify-continue"));
    await waitFor(() => expect(confirmMutateAsyncMock).toHaveBeenCalledWith("abc123"));
    await waitFor(() =>
      expect(navigateMock).toHaveBeenCalledWith("/", { replace: true }),
    );
  });

  it("shows the link's already expired when the GET itself 410s", () => {
    linkInfoMock.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new ApiError(410, { code: "LINK_DEAD", detail: "This link has been used." }),
    });
    renderVerify();
    expect(screen.getByText(/link has expired/i)).toBeInTheDocument();
    expect(screen.getByTestId("access-verify-retry")).toBeInTheDocument();
    expect(screen.queryByTestId("access-verify-continue")).not.toBeInTheDocument();
  });

  it("shows an inline expired notice when the POST comes back 410", async () => {
    linkInfoMock.mockReturnValue({
      data: { address: "person@example.com" },
      isLoading: false,
      isError: false,
    });
    confirmMutateAsyncMock.mockRejectedValue(
      new ApiError(410, { code: "LINK_DEAD", detail: "This link has been used." }),
    );
    const user = userEvent.setup();
    renderVerify();
    await user.click(screen.getByTestId("access-verify-continue"));
    await waitFor(() =>
      expect(screen.getByTestId("access-verify-error")).toHaveTextContent(
        "This link has been used.",
      ),
    );
    expect(screen.getByTestId("access-verify-error-retry")).toBeInTheDocument();
  });
});
