/**
 * The three sibling dashboards — SearchForAlpha, 13F Screener, Congress Trading —
 * and the one URL per app that opens it on a ticker.
 *
 * The same file lives in all three repos (only `SELF` differs); the contract it
 * implements is docs/cross-app-links.md.
 *
 * Owner-only, and never towards a demo: links point at the production copies
 * (`PROD_URLS`, each behind the owner's login) unless a build-time `VITE_*`
 * variable says otherwise (an empty one hides that app), any `*.demos.*`
 * address is refused, and `SiblingApps.tsx` renders nothing on the public demo
 * or for a visitor who is not signed in. Every link carries `?from=<self>` so
 * the receiving app can offer a "Back to …" link.
 */

export type SiblingKey = "sfa" | "13f" | "congress";

export const SELF: SiblingKey = "congress";

type SiblingSpec = {
  label: string;
  prodUrl: string;
  envUrl: () => string | undefined;
  tickerPath: (symbol: string) => string;
};

const SPECS: Record<SiblingKey, SiblingSpec> = {
  sfa: {
    label: "SearchForAlpha",
    prodUrl: "https://alpha.noeinsolutions.com",
    envUrl: () => import.meta.env.VITE_SEARCHFORALPHA_URL as string | undefined,
    tickerPath: (s) => `/ticker/${encodeURIComponent(s)}`,
  },
  "13f": {
    label: "13F Screener",
    prodUrl: "https://13f.noeinsolutions.com",
    envUrl: () => import.meta.env.VITE_13F_URL as string | undefined,
    tickerPath: (s) => `/holdings-search?q=${encodeURIComponent(s)}`,
  },
  congress: {
    label: "Congress Trading",
    prodUrl: "https://congress.noeinsolutions.com",
    envUrl: () => import.meta.env.VITE_CONGRESS_URL as string | undefined,
    tickerPath: (s) => `/tickers?ticker=${encodeURIComponent(s)}`,
  },
};

export const SIBLING_KEYS: readonly SiblingKey[] = ["sfa", "13f", "congress"];

export function siblingLabel(key: SiblingKey): string {
  return SPECS[key].label;
}

const DEMO_HOST = /\.demos\./i;

/** The sibling's root URL: production unless overridden; null if hidden or a demo. */
export function siblingBaseUrl(key: SiblingKey): string | null {
  const override = SPECS[key].envUrl();
  const raw = override === undefined ? SPECS[key].prodUrl : override;
  const url = raw.trim().replace(/\/+$/, "");
  return url && !DEMO_HOST.test(url) ? url : null;
}

/** The other apps this build knows a URL for, in a stable order. */
export function configuredSiblings(): SiblingKey[] {
  return SIBLING_KEYS.filter((k) => k !== SELF && siblingBaseUrl(k) !== null);
}

/** The sibling's page for `ticker` (its home without one), or null if unconfigured. */
export function siblingUrl(key: SiblingKey, ticker?: string | null): string | null {
  const base = siblingBaseUrl(key);
  if (!base) return null;
  const symbol = (ticker ?? "").trim().toUpperCase();
  const path = symbol ? SPECS[key].tickerPath(symbol) : "/";
  return `${base}${path}${path.includes("?") ? "&" : "?"}from=${SELF}`;
}

const FROM_STORAGE_KEY = "sibling-apps:from";

function isSiblingKey(value: string | null): value is SiblingKey {
  return value !== null && value !== SELF && (SIBLING_KEYS as readonly string[]).includes(value);
}

/**
 * Which sibling sent the visitor here, if any. Read from `?from=` on arrival
 * and remembered for the tab's session, since in-app navigation drops the
 * query string.
 */
export function arrivedFrom(search: string): SiblingKey | null {
  const fromParam = new URLSearchParams(search).get("from");
  try {
    if (isSiblingKey(fromParam)) {
      window.sessionStorage.setItem(FROM_STORAGE_KEY, fromParam);
      return fromParam;
    }
    const stored = window.sessionStorage.getItem(FROM_STORAGE_KEY);
    return isSiblingKey(stored) ? stored : null;
  } catch {
    // Storage blocked (private mode, sandboxed iframe): fall back to the URL only.
    return isSiblingKey(fromParam) ? fromParam : null;
  }
}
