import { Text } from "@mantine/core";

import { MemberLink } from "@/components/MemberLink";
import { splitMemberNames } from "@/utils/entityLinks";

type MemberNamesLinksProps = {
  names: string | null | undefined;
};

/** Render a comma-joined member-name blob as individual MemberLinks. */
export function MemberNamesLinks({ names }: MemberNamesLinksProps) {
  const parts = splitMemberNames(names ?? "");
  if (!parts.length) return <Text span size="sm">—</Text>;
  return (
    <Text span size="sm">
      {parts.map((name, i) => (
        <span key={`${name}-${i}`}>
          {i > 0 ? ", " : null}
          <MemberLink name={name} />
        </span>
      ))}
    </Text>
  );
}
