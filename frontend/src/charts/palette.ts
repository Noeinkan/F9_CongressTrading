/**
 * One colour per trade direction on every chart. The hexes are Mantine's
 * teal-7 / red-7, the same pair the direction badges, the Raw table tint and
 * the Home range text already use, so a buy reads the same everywhere.
 */
export const DIRECTION_COLOR = {
  buy: "#0ca678",
  sell: "#f03e3e",
  /** A sale of part of a holding: still a sell, a shade apart. */
  sellPartial: "#e8590c",
  exchange: "#1d4ed8",
  other: "#94a3b8",
} as const;

/** Colour per `transaction_type_label`, for charts that plot one dot per trade. */
export const TRADE_TYPE_COLOR: Record<string, string> = {
  Buy: DIRECTION_COLOR.buy,
  Sell: DIRECTION_COLOR.sell,
  "Sell (partial)": DIRECTION_COLOR.sellPartial,
  Exchange: DIRECTION_COLOR.exchange,
  Unknown: "#64748b",
};
