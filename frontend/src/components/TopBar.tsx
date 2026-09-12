import { Group, Text } from "@mantine/core";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import { useMemo } from "react";

import { DonateButton } from "./DonateButton";
import { FeedbackButton } from "./FeedbackButton";
import { UserMenu } from "./UserMenu";
import { useDemoStatus } from "@/api/demo";
import { useIsMobile } from "@/hooks/useMediaQuery";

export const NAV_ITEMS = [
  { to: "/", label: "Home" },
  { to: "/executive", label: "Executive" },
  { to: "/members", label: "Members" },
  { to: "/tickers", label: "Tickers" },
  { to: "/patterns", label: "Patterns" },
  { to: "/review", label: "Review Queue" },
  { to: "/raw", label: "Raw Data" },
] as const;

export type NavItem = (typeof NAV_ITEMS)[number];

type TopBarProps = {
  onToggleNavbar: () => void;
  navbarOpen: boolean;
};

const burgerStyle = {
  background: "transparent",
  border: "1px solid var(--mantine-color-gray-3)",
  borderRadius: 4,
  padding: "4px 8px",
  cursor: "pointer",
  fontSize: 18,
  lineHeight: 1,
} as const;

export function TopBar({ onToggleNavbar, navbarOpen }: TopBarProps) {
  const location = useLocation();
  const isMobile = useIsMobile();
  const navItems = useVisibleNavItems();

  return (
    <Group h="100%" px="md" justify="space-between" wrap="nowrap" gap="sm">
      <Group gap="sm" wrap="nowrap">
        <button
          type="button"
          onClick={onToggleNavbar}
          aria-label={navbarOpen ? "Close sidebar" : "Open sidebar"}
          aria-expanded={navbarOpen}
          data-testid="topbar-burger"
          style={burgerStyle}
        >
          {navbarOpen ? "✕" : "☰"}
        </button>
        <Text
          component={Link}
          to="/"
          fw={700}
          fz="lg"
          c="navy.7"
          style={{ textDecoration: "none" }}
        >
          Congress Trading
        </Text>
      </Group>
      {!isMobile ? (
        <Group gap="md" component="nav" aria-label="Dashboard pages">
          {navItems.map((item) => (
            <NavLink key={item.to} item={item} active={isActive(location.pathname, item.to)} />
          ))}
        </Group>
      ) : null}
      <Group gap="sm" wrap="nowrap">
        <FeedbackButton />
        <DonateButton />
        <UserMenu />
      </Group>
    </Group>
  );
}

/**
 * Nav minus whatever the demo snapshot has no data for.
 *
 * The Executive page needs OGE filings the frozen capture does not contain, and
 * a nav item leading to a blank page makes a demo read as broken rather than as
 * deliberately limited. Off-demo this returns every item, unchanged.
 */
export function useVisibleNavItems(): readonly NavItem[] {
  const { data } = useDemoStatus();
  return useMemo(() => {
    const hidden = data?.enabled ? data.hiddenRoutes ?? [] : [];
    return hidden.length ? NAV_ITEMS.filter((item) => !hidden.includes(item.to)) : NAV_ITEMS;
  }, [data]);
}

/** Preserve period filters when switching pages so the slice stays shareable. */
function periodSearch(searchParams: URLSearchParams): string {
  const q = new URLSearchParams();
  const lookback = searchParams.get("lookback");
  const quarters = searchParams.get("quarters");
  if (lookback) q.set("lookback", lookback);
  if (quarters) q.set("quarters", quarters);
  const qs = q.toString();
  return qs ? `?${qs}` : "";
}

function NavLink({ item, active }: { item: NavItem; active: boolean }) {
  const [searchParams] = useSearchParams();
  const to = useMemo(
    () => `${item.to}${periodSearch(searchParams)}`,
    [item.to, searchParams],
  );
  return (
    <Text
      component={Link}
      to={to}
      size="sm"
      fw={active ? 600 : 400}
      c={active ? "navy.7" : "dimmed"}
      data-testid={`nav-link-${item.to === "/" ? "home" : item.to.slice(1)}`}
      aria-current={active ? "page" : undefined}
    >
      {item.label}
    </Text>
  );
}

export function isActive(pathname: string, to: string): boolean {
  if (to === "/") {
    return pathname === "/";
  }
  return pathname === to || pathname.startsWith(`${to}/`);
}
