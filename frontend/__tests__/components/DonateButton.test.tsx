import { MantineProvider } from "@mantine/core";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DonateButton } from "@/components/DonateButton";

/**
 * Ko-fi reserves "Donate" / "Donation" / "Charity" wording for registered
 * non-profits and enforces it after the fact. These assertions exist so the
 * banned wording cannot come back through a later edit — the internal class
 * name and `data-testid` are not user-facing and are deliberately not checked.
 */
describe("Ko-fi support link", () => {
  it("reads 'Support' in the label, title and aria-label", () => {
    render(
      <MantineProvider>
        <DonateButton />
      </MantineProvider>,
    );
    const link = screen.getByTestId("topbar-donate");
    expect(link).toHaveTextContent("Support");
    expect(link).toHaveAttribute("title", "Support this project on Ko-fi");
    expect(link).toHaveAttribute("aria-label", "Support this project on Ko-fi");
  });

  it("uses no donation wording anywhere a visitor can read it", () => {
    render(
      <MantineProvider>
        <DonateButton />
      </MantineProvider>,
    );
    const link = screen.getByTestId("topbar-donate");
    const visible = [
      link.textContent ?? "",
      link.getAttribute("title") ?? "",
      link.getAttribute("aria-label") ?? "",
    ].join(" ");
    expect(visible).not.toMatch(/donat|charity/i);
  });

  it("opens Ko-fi in a new tab without leaking the referrer window", () => {
    render(
      <MantineProvider>
        <DonateButton />
      </MantineProvider>,
    );
    const link = screen.getByTestId("topbar-donate");
    expect(link).toHaveAttribute("href", expect.stringContaining("ko-fi.com/"));
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", expect.stringContaining("noopener"));
  });
});
