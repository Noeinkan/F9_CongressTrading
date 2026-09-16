import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { emitDemoRefusal } from "@/api/client";
import { DemoWall } from "@/components/DemoWall";

const navigateMock = vi.fn();
vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => navigateMock };
});

const useDemoStatusMock = vi.fn();
vi.mock("@/api/demo", () => ({
  demoQueryKey: ["demo", "status"],
  useDemoStatus: () => useDemoStatusMock(),
}));

function renderWall(initialPath = "/members") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidateSpy = vi.spyOn(client, "invalidateQueries");
  const utils = render(
    <QueryClientProvider client={client}>
      <MantineProvider>
        <MemoryRouter initialEntries={[initialPath]}>
          <DemoWall />
        </MemoryRouter>
      </MantineProvider>
    </QueryClientProvider>,
  );
  return { ...utils, invalidateSpy };
}

describe("DemoWall", () => {
  beforeEach(() => {
    navigateMock.mockReset();
    useDemoStatusMock.mockReturnValue({
      data: {
        enabled: true,
        contactEmail: "support@noeinsolutions.com",
        locked: [
          {
            feature: "csv_export",
            label: "CSV downloads",
            message: "CSV export needs full access.",
          },
          {
            feature: "review_actions",
            label: "Review-queue actions",
            message: "Review actions need full access.",
          },
        ],
      },
    });
  });

  it("opens a modal for DEMO_LOCKED, leading with the feature's label and the server's message", async () => {
    renderWall();
    act(() => {
      emitDemoRefusal({
        code: "DEMO_LOCKED",
        feature: "csv_export",
        detail: "CSV export needs full access.",
      });
    });
    // Mantine's Modal mounts its content one tick after `opened` flips (its
    // enter transition), so the message only appears once that settles —
    // `findBy*` retries until then, unlike a single `getBy*`.
    expect(await screen.findByText(/CSV downloads/)).toBeInTheDocument();
    expect(await screen.findByTestId("demo-wall-message")).toHaveTextContent(
      "CSV export needs full access.",
    );
    expect(screen.getByTestId("demo-wall-contact")).toHaveAttribute(
      "href",
      "mailto:support@noeinsolutions.com",
    );
  });

  it("opens the same modal for DEMO_READ_ONLY, with the server's detail", async () => {
    renderWall();
    act(() => {
      emitDemoRefusal({ code: "DEMO_READ_ONLY", detail: "This demo is read-only." });
    });
    expect(await screen.findByTestId("demo-wall-message")).toHaveTextContent(
      "This demo is read-only.",
    );
  });

  it("invalidates the status query and redirects to /access on DEMO_SIGNED_OUT", async () => {
    const { invalidateSpy } = renderWall("/members");
    act(() => {
      emitDemoRefusal({ code: "DEMO_SIGNED_OUT", detail: "Sign in again." });
    });
    await waitFor(() =>
      expect(navigateMock).toHaveBeenCalledWith(expect.stringMatching(/^\/access\?next=/)),
    );
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["demo", "status"] });
  });

  it("invalidates the status query and redirects to /access/ended on DEMO_EXPIRED", async () => {
    const { invalidateSpy } = renderWall();
    act(() => {
      emitDemoRefusal({ code: "DEMO_EXPIRED", detail: "Time is up.", revoked: false });
    });
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith("/access/ended"));
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["demo", "status"] });
  });
});
