import { useMediaQuery as useMantineMediaQuery } from "@mantine/hooks";

/** Breakpoint name → Mantine media query (matches Mantine v8 default breakpoints). */
export type Breakpoint = "xs" | "sm" | "md" | "lg" | "xl";

const QUERIES: Record<Breakpoint, string> = {
  xs: "(max-width: 575.98px)",
  sm: "(min-width: 576px)",
  md: "(min-width: 768px)",
  lg: "(min-width: 992px)",
  xl: "(min-width: 1200px)",
};

/**
 * Mantine's `useMediaQuery` returns `false` on the server (and during the first
 * client render under jsdom tests where `matchMedia` matches the stub in
 * `__tests__/setup.ts`). Tests that need a deterministic value should
 * `vi.spyOn(useMediaQuery, "useMediaQuery").mockReturnValue(true)` via
 * Mantine's actual import path.
 */
export function useMediaQuery(breakpoint: Breakpoint): boolean {
  return useMantineMediaQuery(QUERIES[breakpoint]);
}

/** True on small viewports (phones). Used by the shell to switch to burger nav. */
export function useIsMobile(): boolean {
  return !useMediaQuery("sm");
}
