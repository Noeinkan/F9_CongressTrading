import { Badge, type MantineColor } from "@mantine/core";

import { classifyTransaction, directionColor, rangeOpacity } from "@/utils/transactions";

type Variant = "filled" | "light" | "outline";

function bucketVariant(opacity: number): Variant {
  // Trade-size bucket drives the Mantine badge variant — small trades use
  // a quiet outline, mid-size trades get a soft "light" fill, large trades
  // get a vivid "filled" badge. The exact thresholds match the
  // amount-bucket convention used by `rangeOpacity`.
  if (opacity >= 0.95) return "filled";
  if (opacity >= 0.7) return "light";
  return "outline";
}

type DirectionBadgeProps = {
  label: string;
  amountRangeRaw?: string | null;
  size?: "xs" | "sm" | "md" | "lg";
  testId?: string;
};

/**
 * A single-direction (Buy or Sell) badge whose color reflects the trade
 * direction (teal = buy, red = sell) and whose variant reflects the
 * trade-size bucket (filled = largest, outline = smallest).
 */
export function DirectionBadge({
  label,
  amountRangeRaw,
  size = "sm",
  testId,
}: DirectionBadgeProps) {
  const direction = classifyTransaction(label);
  const color: MantineColor = (directionColor(direction) as MantineColor) ?? "gray";
  const opacity = rangeOpacity(amountRangeRaw);
  const variant = bucketVariant(opacity);
  const dataAttrs: Record<string, string> = { "data-direction": direction };
  if (testId) dataAttrs["data-testid"] = testId;
  return (
    <Badge color={color} variant={variant} size={size} {...dataAttrs}>
      {label}
    </Badge>
  );
}
