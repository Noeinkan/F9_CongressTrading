import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/api/client";
import { Access } from "@/routes/Access";

const navigateMock = vi.fn();
vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => navigateMock };
});

const useDemoStatusMock = vi.fn();
const requestMutateAsyncMock = vi.fn();
const codeMutateAsyncMock = vi.fn();
vi.mock("@/api/demo", () => ({
  demoQueryKey: ["demo", "status"],
  useDemoStatus: () => useDemoStatusMock(),
  useDemoAccessRequest: () => ({ mutateAsync: requestMutateAsyncMock, isPending: false }),
  useDemoAccessCode: () => ({ mutateAsync: codeMutateAsyncMock, isPending: false }),
}));

function renderAccess(initialPath = "/access") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MantineProvider>
        <MemoryRouter initialEntries={[initialPath]}>
          <Access />
        </MemoryRouter>
      </MantineProvider>
    </QueryClientProvider>,
  );
}

describe("Access", () => {
  beforeEach(() => {
    navigateMock.mockReset();
    requestMutateAsyncMock.mockReset();
    codeMutateAsyncMock.mockReset();
    useDemoStatusMock.mockReturnValue({
      data: {
        enabled: true,
        snapshotLabel: "Snapshot: 12 September 2026",
        session: { minutes: 45 },
        access: {
          gate: true,
          codeMinutes: 15,
          privacy: [
            { title: "What is stored.", text: "Your email and the code." },
            { title: "Why.", text: "So we can let you in." },
            { title: "For how long.", text: "One year." },
          ],
        },
      },
    });
  });

  it("shows the 45-minute headline, taken from the server, and the privacy paragraphs", () => {
    renderAccess();
    expect(screen.getByText(/free for 45 minutes/i)).toBeInTheDocument();
    expect(screen.getByText("What is stored.")).toBeInTheDocument();
    expect(screen.getByText(/Your email and the code\./)).toBeInTheDocument();
  });

  it("moves from the email step to the code step on a successful request", async () => {
    requestMutateAsyncMock.mockResolvedValue({
      status: "sent",
      address: "person@example.com",
      codeMinutes: 15,
    });
    const user = userEvent.setup();
    renderAccess();
    await user.type(screen.getByTestId("access-email-input"), "person@example.com");
    await user.click(screen.getByTestId("access-email-submit"));
    await waitFor(() => expect(screen.getByTestId("access-code-step")).toBeInTheDocument());
    expect(screen.getByText(/check your inbox/i)).toBeInTheDocument();
    expect(screen.getByText(/person@example.com/)).toBeInTheDocument();
  });

  it("shows the mail error and does NOT claim the inbox got anything on MAIL_FAILED", async () => {
    requestMutateAsyncMock.mockRejectedValue(
      new ApiError(503, { code: "MAIL_FAILED", detail: "The mail relay is down." }),
    );
    const user = userEvent.setup();
    renderAccess();
    await user.type(screen.getByTestId("access-email-input"), "person@example.com");
    await user.click(screen.getByTestId("access-email-submit"));
    await waitFor(() =>
      expect(screen.getByTestId("access-request-error")).toHaveTextContent(
        "The mail relay is down.",
      ),
    );
    expect(screen.queryByTestId("access-code-step")).not.toBeInTheDocument();
    expect(screen.queryByText(/check your inbox/i)).not.toBeInTheDocument();
  });

  it("shows attempts left on WRONG_CODE without leaving the code step", async () => {
    requestMutateAsyncMock.mockResolvedValue({
      status: "sent",
      address: "person@example.com",
      codeMinutes: 15,
    });
    codeMutateAsyncMock.mockRejectedValue(
      new ApiError(400, { code: "WRONG_CODE", detail: "That code is wrong.", attemptsLeft: 3 }),
    );
    const user = userEvent.setup();
    renderAccess();
    await user.type(screen.getByTestId("access-email-input"), "person@example.com");
    await user.click(screen.getByTestId("access-email-submit"));
    await waitFor(() => expect(screen.getByTestId("access-code-step")).toBeInTheDocument());
    await user.type(screen.getByTestId("access-code-input"), "000000");
    await user.click(screen.getByTestId("access-code-submit"));
    await waitFor(() =>
      expect(screen.getByTestId("access-code-error")).toHaveTextContent("That code is wrong."),
    );
    expect(screen.getByTestId("access-code-error")).toHaveTextContent("3 attempts left");
    expect(screen.getByTestId("access-code-step")).toBeInTheDocument();
  });

  it("offers a way back to the email step on CODE_DEAD", async () => {
    requestMutateAsyncMock.mockResolvedValue({
      status: "sent",
      address: "person@example.com",
      codeMinutes: 15,
    });
    codeMutateAsyncMock.mockRejectedValue(
      new ApiError(400, { code: "CODE_DEAD", detail: "That code no longer works." }),
    );
    const user = userEvent.setup();
    renderAccess();
    await user.type(screen.getByTestId("access-email-input"), "person@example.com");
    await user.click(screen.getByTestId("access-email-submit"));
    await waitFor(() => expect(screen.getByTestId("access-code-step")).toBeInTheDocument());
    await user.type(screen.getByTestId("access-code-input"), "000000");
    await user.click(screen.getByTestId("access-code-submit"));
    await waitFor(() => expect(screen.getByTestId("access-code-dead-retry")).toBeInTheDocument());
    await user.click(screen.getByTestId("access-code-dead-retry"));
    expect(screen.getByTestId("access-email-step")).toBeInTheDocument();
  });

  it("navigates to a validated next path on a successful code", async () => {
    requestMutateAsyncMock.mockResolvedValue({
      status: "sent",
      address: "person@example.com",
      codeMinutes: 15,
    });
    codeMutateAsyncMock.mockResolvedValue({
      status: "ok",
      access: { gate: true, status: "active" },
    });
    const user = userEvent.setup();
    renderAccess("/access?next=%2Fmembers%3Fmember%3DAlice");
    await user.type(screen.getByTestId("access-email-input"), "person@example.com");
    await user.click(screen.getByTestId("access-email-submit"));
    await waitFor(() => expect(screen.getByTestId("access-code-step")).toBeInTheDocument());
    await user.type(screen.getByTestId("access-code-input"), "123456");
    await user.click(screen.getByTestId("access-code-submit"));
    await waitFor(() =>
      expect(navigateMock).toHaveBeenCalledWith("/members?member=Alice", { replace: true }),
    );
  });

  it("falls back to / when next is not a same-site path", async () => {
    requestMutateAsyncMock.mockResolvedValue({
      status: "sent",
      address: "person@example.com",
      codeMinutes: 15,
    });
    codeMutateAsyncMock.mockResolvedValue({
      status: "ok",
      access: { gate: true, status: "active" },
    });
    const user = userEvent.setup();
    renderAccess("/access?next=" + encodeURIComponent("//evil.example.com"));
    await user.type(screen.getByTestId("access-email-input"), "person@example.com");
    await user.click(screen.getByTestId("access-email-submit"));
    await waitFor(() => expect(screen.getByTestId("access-code-step")).toBeInTheDocument());
    await user.type(screen.getByTestId("access-code-input"), "123456");
    await user.click(screen.getByTestId("access-code-submit"));
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith("/", { replace: true }));
  });

  it("redirects to /access/ended when the code comes back DEMO_EXPIRED", async () => {
    requestMutateAsyncMock.mockResolvedValue({
      status: "sent",
      address: "person@example.com",
      codeMinutes: 15,
    });
    codeMutateAsyncMock.mockRejectedValue(
      new ApiError(403, { code: "DEMO_EXPIRED", detail: "Time is up.", revoked: false }),
    );
    const user = userEvent.setup();
    renderAccess();
    await user.type(screen.getByTestId("access-email-input"), "person@example.com");
    await user.click(screen.getByTestId("access-email-submit"));
    await waitFor(() => expect(screen.getByTestId("access-code-step")).toBeInTheDocument());
    await user.type(screen.getByTestId("access-code-input"), "123456");
    await user.click(screen.getByTestId("access-code-submit"));
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith("/access/ended"));
  });
});
