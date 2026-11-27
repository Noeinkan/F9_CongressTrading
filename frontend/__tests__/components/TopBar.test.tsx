import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TopBar } from "@/components/TopBar";

vi.mock("@/hooks/useMediaQuery", async () => {
  const actual =
    await vi.importActual<typeof import("@/hooks/useMediaQuery")>(
      "@/hooks/useMediaQuery",
    );
  return {
    ...actual,
    useIsMobile: () => false,
  };
});

const useSessionQueryMock = vi.fn();
vi.mock("@/api/auth", () => ({
  useSessionQuery: () => useSessionQueryMock(),
  useLogout: () => ({ mutate: vi.fn(), isPending: false }),
}));

// TopBar filters its nav by the demo status, so it is a query consumer now.
// Mocked rather than wrapped in a QueryClientProvider, matching the auth mock
// above: these tests are about the bar, not about data fetching.
const useDemoStatusMock = vi.fn();
vi.mock("@/api/demo", () => ({
  useDemoStatus: () => useDemoStatusMock(),
}));

// The refresh control polls the API; stub it so the bar renders without a client.
vi.mock("@/components/RefreshControl", () => ({
  RefreshControl: () => <div data-testid="topbar-refresh" />,
}));

function renderTopBar(path = "/") {
  return render(
    <MantineProvider>
      <MemoryRouter initialEntries={[path]}>
        <TopBar />
      </MemoryRouter>
    </MantineProvider>,
  );
}

describe("TopBar", () => {
  beforeEach(() => {
    useSessionQueryMock.mockReturnValue({
      data: { authenticated: true, auth_required: true, user: "admin" },
    });
    useDemoStatusMock.mockReturnValue({ data: { enabled: false } });
  });

  it("shows the brand", () => {
    renderTopBar();
    expect(screen.getByText(/congress trading/i)).toBeInTheDocument();
  });

  it("has no sidebar toggle or pages menu on desktop", () => {
    renderTopBar();
    expect(screen.queryByTestId("topbar-burger")).not.toBeInTheDocument();
    expect(screen.queryByTestId("topbar-pages-menu")).not.toBeInTheDocument();
  });

  it("shows the refresh control off-demo", () => {
    renderTopBar();
    expect(screen.getByTestId("topbar-refresh")).toBeInTheDocument();
  });

  it("hides the refresh control on the demo", () => {
    useDemoStatusMock.mockReturnValue({ data: { enabled: true, hiddenRoutes: [] } });
    renderTopBar();
    expect(screen.queryByTestId("topbar-refresh")).not.toBeInTheDocument();
  });

  it("shows all 6 nav links on desktop", () => {
    renderTopBar();
    expect(screen.getByTestId("nav-link-home")).toHaveTextContent("Home");
    expect(screen.getByTestId("nav-link-members")).toHaveTextContent("Members");
    expect(screen.getByTestId("nav-link-tickers")).toHaveTextContent("Tickers");
    expect(screen.getByTestId("nav-link-patterns")).toHaveTextContent("Patterns");
    expect(screen.getByTestId("nav-link-review")).toHaveTextContent("Review Queue");
    expect(screen.getByTestId("nav-link-raw")).toHaveTextContent("Raw Data");
  });

  it("keeps every nav link when the deployment is not the demo", () => {
    renderTopBar();
    expect(screen.getByTestId("nav-link-executive")).toBeInTheDocument();
    expect(screen.getByTestId("nav-link-senate")).toHaveTextContent("Senate");
  });

  it("drops the routes the demo snapshot has no data for", () => {
    useDemoStatusMock.mockReturnValue({
      data: { enabled: true, hiddenRoutes: ["/executive"] },
    });
    renderTopBar();
    expect(screen.queryByTestId("nav-link-executive")).not.toBeInTheDocument();
    // Everything else survives — this hides empty pages, not the dashboard.
    expect(screen.getByTestId("nav-link-members")).toBeInTheDocument();
    expect(screen.getByTestId("nav-link-raw")).toBeInTheDocument();
  });

  it("marks the active link with aria-current", () => {
    renderTopBar("/members");
    expect(screen.getByTestId("nav-link-members")).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByTestId("nav-link-home")).not.toHaveAttribute("aria-current");
  });

  it("treats nested paths as belonging to their parent page", () => {
    renderTopBar("/members/someone");
    expect(screen.getByTestId("nav-link-members")).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  it("renders the Support CTA as an external link to Ko-fi", () => {
    renderTopBar();
    const link = screen.getByTestId("topbar-donate");
    // "Support", never "Donate": Ko-fi reserves donation wording for
    // registered non-profits. See DonateButton.test.tsx.
    expect(link).toHaveTextContent("Support");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(link.getAttribute("href")).toMatch(/^https:\/\/ko-fi\.com\//);
  });

  it("renders the Feedback trigger next to the Support CTA", () => {
    renderTopBar();
    expect(screen.getByTestId("topbar-feedback")).toHaveTextContent("Feedback");
  });
});
