import { Anchor, type AnchorProps } from "@mantine/core";
import { Link } from "react-router-dom";

import { tickerHref } from "@/utils/entityLinks";

type TickerLinkProps = Omit<AnchorProps, "component" | "href"> & {
  ticker: string | null | undefined;
  override?: string;
  children?: React.ReactNode;
};

/** Internal link to `/tickers?ticker=…`. Renders nothing when ticker is empty. */
export function TickerLink({
  ticker,
  override,
  children,
  size = "sm",
  ...rest
}: TickerLinkProps) {
  const trimmed = (ticker ?? "").trim();
  if (!trimmed) return null;
  return (
    <Anchor component={Link} to={tickerHref(trimmed, override)} size={size} {...rest}>
      {children ?? trimmed}
    </Anchor>
  );
}
