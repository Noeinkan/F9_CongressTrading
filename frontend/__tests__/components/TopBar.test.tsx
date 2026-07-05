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

function renderTopBar(path = "/") {
  return render(
    <MantineProvider>
      <MemoryRouter initialEntries={[path]}>
        <TopBar onToggleNavbar={vi.fn()} navbarOpen={true} />
      </MemoryRouter>
    </MantineProvider>,
  );
}

describe("TopBar", () => {
  beforeEach(() => {
    useSessionQueryMock.mockReturnValue({
      data: { authenticated: true, auth_required: true, user: "admin" },
    });
  });

  it("shows the brand", () => {
    renderTopBar();
    expect(screen.getByText(/congress trading/i)).toBeInTheDocument();
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

  it("renders the Donate CTA as an external link to Ko-fi", () => {
    renderTopBar();
    const link = screen.getByTestId("topbar-donate");
    expect(link).toHaveTextContent("Donate");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(link.getAttribute("href")).toMatch(/^https:\/\/ko-fi\.com\//);
  });
});
