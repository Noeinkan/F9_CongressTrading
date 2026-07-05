/**
 * Render a date as DD/MM/YYYY. Input is the ISO `YYYY-MM-DD` string the API
 * returns (timestamps may include a time suffix — slice the first 10 chars).
 * Falls back to the raw value if it doesn't look like an ISO date so callers
 * never crash on unexpected shapes.
 */
export function formatDate(value: unknown): string {
  if (value == null || value === "") return "—";
  const s = String(value);
  if (s.length < 10 || s[4] !== "-" || s[7] !== "-") return s;
  const yyyy = s.slice(0, 4);
  const mm = s.slice(5, 7);
  const dd = s.slice(8, 10);
  if (!/^\d{4}$/.test(yyyy) || !/^\d{2}$/.test(mm) || !/^\d{2}$/.test(dd)) return s;
  return `${dd}/${mm}/${yyyy}`;
}

export function formatCurrency(value: unknown): string {
  if (value == null || value === "") return "—";
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  if (n === 0) return "—";
  const sign = n < 0 ? "-" : "";
  const abs = Math.abs(n);
  if (abs >= 1_000_000) return `${sign}$${(abs / 1_000_000).toFixed(1)}M`;
  if (abs >= 1_000) return `${sign}$${(abs / 1_000).toFixed(1)}K`;
  return `${sign}$${abs.toLocaleString()}`;
}

export function formatNumber(value: unknown, decimals = 2): string {
  if (value == null || value === "") return "—";
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return n.toFixed(decimals);
}

export function formatDisclosedRange(low: unknown, high: unknown): string {
  const lo = formatCurrency(low);
  const hi = formatCurrency(high);
  if (lo === "—" && hi === "—") return "—";
  return `${lo} – ${hi}`;
}

export function formatCount(value: unknown): string {
  if (value == null) return "—";
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return n.toLocaleString();
}

export function formatPercent(value: unknown, decimals = 0): string {
  if (value == null) return "—";
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return `${(n * (n <= 1 ? 100 : 1)).toFixed(decimals)}%`.replace(/\.0%$/, "%");
}

/**
 * Format a signed percentage that is already expressed in percent units
 * (e.g. 12.4 means +12.4%, -7.1 means -7.1%). Returns "—" for null/NaN.
 */
export function formatSignedPercent(value: unknown, decimals = 1): string {
  if (value == null) return "—";
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  const sign = n > 0 ? "+" : n < 0 ? "" : "";
  return `${sign}${n.toFixed(decimals)}%`.replace(/\.0%$/, "%");
}

/**
 * Mantine color for a signed return — green for positive, red for negative,
 * dimmed gray for zero. Used by the ROI column on the Tickers / Members
 * leaderboards and the per-trade history rows.
 */
export function returnColor(value: unknown): string {
  if (value == null) return "dimmed";
  const n = Number(value);
  if (!Number.isFinite(n) || n === 0) return "dimmed";
  return n > 0 ? "teal" : "red";
}

export function yahooFinanceQuoteUrl(ticker: string): string {
  return `https://finance.yahoo.com/quote/${encodeURIComponent(ticker.trim().toUpperCase())}`;
}

export function msnMoneyQuoteUrl(ticker: string): string {
  return `https://www.msn.com/en-us/money/stockdetails/fi-${encodeURIComponent(ticker.trim().toUpperCase())}`;
}

const SEARCH_FOR_ALPHA_DEFAULT_URL = "http://77.42.70.26:8060";

/**
 * Base URL for the SearchForAlpha Lab (F2) dashboard. Override with
 * `VITE_SEARCHFORALPHA_URL` at build time (trailing slash stripped).
 */
export function searchForAlphaBaseUrl(): string {
  const raw = import.meta.env.VITE_SEARCHFORALPHA_URL ?? SEARCH_FOR_ALPHA_DEFAULT_URL;
  return raw.replace(/\/+$/, "");
}

/**
 * Build the SearchForAlpha Lab (F2) ticker page URL, e.g.
 * `http://77.42.70.26:8060/ticker/NVDA`. If the ticker is empty, returns
 * `{base}/ticker/` (used when the button is disabled).
 */
export function searchForAlphaUrl(ticker: string): string {
  const base = searchForAlphaBaseUrl();
  const symbol = ticker.trim().toUpperCase();
  if (!symbol) return `${base}/ticker/`;
  return `${base}/ticker/${encodeURIComponent(symbol)}`;
}

const KOFI_DEFAULT_URL = "https://ko-fi.com/noeinkan";

/**
 * URL for the project sponsor's Ko-fi page. Override with `VITE_KOFI_URL`
 * at build time (e.g. `https://ko-fi.com/yourname`). The header Donate
 * button is only rendered when this resolves to a non-empty Ko-fi URL.
 */
export function kofiUrl(): string {
  const raw = (import.meta.env.VITE_KOFI_URL ?? KOFI_DEFAULT_URL).trim();
  return raw.replace(/\/+$/, "");
}

/** True when the donate button has a valid Ko-fi URL configured. */
export function hasKofiUrl(): boolean {
  return kofiUrl().length > 0;
}
