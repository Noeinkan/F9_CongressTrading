import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AccessEnded } from "@/routes/AccessEnded";

const navigateMock = vi.fn();
vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => navigateMock };
});

const useDemoStatusMock = vi.fn();
const signOutMutateAsyncMock = vi.fn();
vi.mock("@/api/demo", () => ({
  demoQueryKey: ["demo", "status"],
  useDemoStatus: () => useDemoStatusMock(),
  useDemoSignOut: () => ({ mutateAsync: signOutMutateAsyncMock }),
}));

function renderEnded() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MantineProvider>
        <MemoryRouter initialEntries={["/access/ended"]}>
          <AccessEnded />
        </MemoryRouter>
      </MantineProvider>
    </QueryClientProvider>,
  );
}

describe("AccessEnded", () => {
  beforeEach(() => {
    navigateMock.mockReset();
    signOutMutateAsyncMock.mockReset();
    signOutMutateAsyncMock.mockResolvedValue({ ok: true });
  });

  it("says the minutes are up and names what the visitor saw", () => {
    useDemoStatusMock.mockReturnValue({
      data: {
        enabled: true,
        contactEmail: "support@noeinsolutions.com",
        session: { minutes: 45 },
        access: { gate: true, status: "ended" },
      },
    });
    renderEnded();
    expect(screen.getByText(/your 45 minutes with the demo are up/i)).toBeInTheDocument();
    expect(screen.getByText(/house and senate disclosures/i)).toBeInTheDocument();
  });

  it("uses the revoked wording when access.status is revoked", () => {
    useDemoStatusMock.mockReturnValue({
      data: {
        enabled: true,
        contactEmail: "support@noeinsolutions.com",
        session: { minutes: 45 },
        access: { gate: true, status: "revoked" },
      },
    });
    renderEnded();
    expect(screen.getByText(/demo access has been switched off/i)).toBeInTheDocument();
    expect(screen.queryByText(/minutes with the demo are up/i)).not.toBeInTheDocument();
  });

  it("never offers to start again", () => {
    useDemoStatusMock.mockReturnValue({
      data: {
        enabled: true,
        contactEmail: "support@noeinsolutions.com",
        session: { minutes: 45 },
        access: { gate: true, status: "ended" },
      },
    });
    renderEnded();
    expect(screen.queryByText(/start again/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/new session/i)).not.toBeInTheDocument();
  });

  it("offers a single onward action: emailing the contact address", () => {
    useDemoStatusMock.mockReturnValue({
      data: {
        enabled: true,
        contactEmail: "support@noeinsolutions.com",
        session: { minutes: 45 },
        access: { gate: true, status: "ended" },
      },
    });
    renderEnded();
    expect(screen.getByTestId("access-ended-contact")).toHaveAttribute(
      "href",
      "mailto:support@noeinsolutions.com",
    );
  });

  it("signs out and returns to /access", async () => {
    useDemoStatusMock.mockReturnValue({
      data: {
        enabled: true,
        contactEmail: "support@noeinsolutions.com",
        session: { minutes: 45 },
        access: { gate: true, status: "ended" },
      },
    });
    const user = userEvent.setup();
    renderEnded();
    await user.click(screen.getByTestId("access-ended-signout"));
    await waitFor(() => expect(signOutMutateAsyncMock).toHaveBeenCalled());
    await waitFor(() =>
      expect(navigateMock).toHaveBeenCalledWith("/access", { replace: true }),
    );
  });
});
