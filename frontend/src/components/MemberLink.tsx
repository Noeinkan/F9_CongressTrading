import { Anchor, type AnchorProps } from "@mantine/core";
import { Link } from "react-router-dom";

import { memberHref } from "@/utils/entityLinks";

type MemberLinkProps = Omit<AnchorProps, "component" | "href"> & {
  name: string | null | undefined;
  /** Extra query params (e.g. `{ view: "committee_relevance" }`). */
  extraParams?: Record<string, string>;
  children?: React.ReactNode;
};

/** Internal link to `/members?member=…`. Renders nothing when name is empty. */
export function MemberLink({
  name,
  extraParams,
  children,
  size = "sm",
  ...rest
}: MemberLinkProps) {
  const trimmed = (name ?? "").trim();
  if (!trimmed) return null;
  return (
    <Anchor component={Link} to={memberHref(trimmed, extraParams)} size={size} {...rest}>
      {children ?? trimmed}
    </Anchor>
  );
}
