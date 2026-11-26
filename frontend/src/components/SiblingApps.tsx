import { Anchor, Button, Menu } from "@mantine/core";
import { useMemo } from "react";
import { useLocation, useSearchParams } from "react-router-dom";

import { useSessionQuery } from "@/api/auth";
import { useDemoStatus } from "@/api/demo";
import {
  type SiblingKey,
  arrivedFrom,
  configuredSiblings,
  siblingLabel,
  siblingUrl,
} from "@/config/siblingApps";

/**
 * The sibling apps this viewer may open: none on the public demo, none for a
 * visitor who is not signed in, and only those this build has a URL for.
 * The dashboard has one account (APP_USERNAME), so signed in means the owner;
 * with auth off it is the owner's own machine.
 */
export function useSiblingApps(): SiblingKey[] {
  const demo = useDemoStatus();
  const session = useSessionQuery();
  return useMemo(() => {
    if (demo.isLoading || demo.data?.enabled) return [];
    const s = session.data;
    if (!s) return [];
    const owner = s.auth_required ? s.authenticated && Boolean(s.user) : true;
    return owner ? configuredSiblings() : [];
  }, [demo.isLoading, demo.data?.enabled, session.data]);
}

/** The ticker the current page is about, if the URL names one. */
function useCurrentTicker(): string {
  const [searchParams] = useSearchParams();
  return (searchParams.get("ticker_override") || searchParams.get("ticker") || "").trim().toUpperCase();
}

/**
 * Header menu that opens the sibling dashboards — on the current ticker when
 * the page has one, on their home page otherwise. Same tab: the sibling shows
 * a "Back to Congress Trading" link.
 */
export function SiblingAppsMenu() {
  const siblings = useSiblingApps();
  const ticker = useCurrentTicker();
  if (siblings.length === 0) return null;
  return (
    <Menu position="bottom-end" withinPortal>
      <Menu.Target>
        <Button variant="subtle" color="gray" size="compact-sm" data-testid="sibling-apps-trigger">
          Apps ▾
        </Button>
      </Menu.Target>
      <Menu.Dropdown>
        <Menu.Label>{ticker ? `Open ${ticker} in` : "Open"}</Menu.Label>
        {siblings.map((key) => (
          <Menu.Item
            key={key}
            component="a"
            href={siblingUrl(key, ticker) ?? undefined}
            data-testid={`sibling-apps-${key}`}
          >
            {siblingLabel(key)}
          </Menu.Item>
        ))}
      </Menu.Dropdown>
    </Menu>
  );
}

/** "← Back to SearchForAlpha" when the owner came from a sibling app. */
export function BackToSibling() {
  const siblings = useSiblingApps();
  const location = useLocation();
  const ticker = useCurrentTicker();
  const from = useMemo(() => arrivedFrom(location.search), [location.search]);
  if (!from || !siblings.includes(from)) return null;
  return (
    <Anchor href={siblingUrl(from, ticker) ?? undefined} size="sm" c="dimmed" data-testid="sibling-back-link">
      ← Back to {siblingLabel(from)}
    </Anchor>
  );
}
