import { Anchor } from "@mantine/core";

import { kofiUrl } from "@/utils/format";

/**
 * Header "Support" CTA that opens the sponsor's Ko-fi page in a new tab.
 * The class `donate-button` (defined in `styles/globals.css`) styles it as
 * a warm amber pill so it stands out from the dimmed nav links.
 *
 * The visible wording must stay "Support" — never "Donate", "Donation" or
 * "Charity". Ko-fi reserves donation wording for registered non-profits and
 * enforces it after the fact (it flagged a sibling dashboard in Aug 2026).
 * That applies to the label, `title` and `aria-label`; the internal class and
 * component names are not user-facing and stay as they are.
 */
export function DonateButton() {
  const url = kofiUrl();
  if (!url) return null;

  return (
    <Anchor
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className="donate-button"
      title="Support this project on Ko-fi"
      aria-label="Support this project on Ko-fi"
      data-testid="topbar-donate"
    >
      Support
    </Anchor>
  );
}