/**
 * Helpers for the Home "Latest activity" table.
 *
 * `transaction_type_label` comes from the API in many forms
 * (e.g. "Buy", "Sale", "Sell (partial)", "Purchase", "Exchange", "Buy (calls)"
 * or even free-text). These helpers map that to a small set of colors for the
 * "Type" cell and parse a `amount_range_raw` string like "$1,001 - $15,000" or
 * "$15K – $50K" into a numeric high value used to derive a row opacity.
 */

export type TransactionDirection = "buy" | "sell" | "other";

const BUY_PATTERN = /\b(buy|purchase|acquire|received|received (?:partial )?gift)\b/i;
const SELL_PATTERN = /\b(sell|sale|sold|exchange|dispose|divest|gift)\b/i;

export function classifyTransaction(label: string | null | undefined): TransactionDirection {
  const text = (label ?? "").toLowerCase();
  if (!text) return "other";
  if (SELL_PATTERN.test(text) && !BUY_PATTERN.test(text)) return "sell";
  if (BUY_PATTERN.test(text)) return "buy";
  // Default ambiguous labels (e.g. "Exchange") to "other".
  return "other";
}

const RANGE_PATTERN = /\$?\s*([\d,]+(?:\.\d+)?)\s*([kKmM])?/g;

/**
 * Extract the largest numeric value found in a range string like
 * "$1,001 - $15,000" or "$15K – $50K". Returns 0 when no number is found.
 */
export function parseRangeHigh(raw: string | null | undefined): number {
  if (!raw) return 0;
  const matches: number[] = [];
  for (const m of raw.matchAll(RANGE_PATTERN)) {
    const rawValue = m[1];
    if (!rawValue) continue;
    const value = Number(rawValue.replace(/,/g, ""));
    if (!Number.isFinite(value)) continue;
    const unit = (m[2] ?? "").toLowerCase();
    const scaled = unit === "k" ? value * 1_000 : unit === "m" ? value * 1_000_000 : value;
    matches.push(scaled);
  }
  return matches.length ? Math.max(...matches) : 0;
}

/**
 * Map a row's range magnitude to an opacity in [0.35, 1].
 * Buckets are conservative; small trades are faded, large ones are vivid.
 */
export function rangeOpacity(raw: string | null | undefined): number {
  const high = parseRangeHigh(raw);
  if (high <= 0) return 0.55;
  if (high < 5_000) return 0.4;
  if (high < 15_000) return 0.55;
  if (high < 50_000) return 0.7;
  if (high < 250_000) return 0.85;
  return 1;
}

/**
 * Mantine badge color per direction. "other" uses gray to avoid misleading
 * users about a row being a buy or a sell.
 */
export function directionColor(direction: TransactionDirection): string {
  if (direction === "buy") return "teal";
  if (direction === "sell") return "red";
  return "gray";
}

/**
 * Background tint for a row, scaled by amount-range magnitude. Used by the
 * Raw Data table to make big trades visually pop without overwhelming small
 * ones. Returns `undefined` for non-buy/sell directions so callers can pass
 * it straight to a `style` prop.
 */
export function directionTint(
  direction: TransactionDirection,
  range: string | null | undefined,
): string | undefined {
  const op = rangeOpacity(range);
  // Floor at 0.08 keeps the smallest traded bucket faintly visible; the
  // ceiling (`0.08 + 0.18 = 0.26`) prevents a $1M row from becoming a
  // solid color block in a striped table.
  if (direction === "buy") return `rgba(45, 212, 191, ${(0.08 + op * 0.18).toFixed(3)})`;
  if (direction === "sell") return `rgba(240, 82, 82, ${(0.08 + op * 0.18).toFixed(3)})`;
  return undefined;
}
