import { Anchor } from "@mantine/core";

import { kofiUrl } from "@/utils/format";

/**
 * Header "Donate" CTA that opens the sponsor's Ko-fi page in a new tab.
 * The class `donate-button` (defined in `styles/globals.css`) styles it as
 * a warm amber pill so it stands out from the dimmed nav links.
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
      aria-label="Donate — support this project on Ko-fi"
      data-testid="topbar-donate"
    >
      Donate
    </Anchor>
  );
}