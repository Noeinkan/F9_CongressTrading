export function formatDate(value: unknown): string {
  if (value == null || value === "") return "—";
  const s = String(value);
  return s.length >= 10 ? s.slice(0, 10) : s;
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

export function yahooFinanceQuoteUrl(ticker: string): string {
  return `https://finance.yahoo.com/quote/${encodeURIComponent(ticker.trim().toUpperCase())}`;
}

export function msnMoneyQuoteUrl(ticker: string): string {
  return `https://www.msn.com/en-us/money/stockdetails/fi-${encodeURIComponent(ticker.trim().toUpperCase())}`;
}
