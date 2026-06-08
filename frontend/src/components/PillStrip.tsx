import { Badge, Group } from "@mantine/core";

type PillItem = {
  label: string;
  count?: number;
  color?: string;
};

type PillStripProps = {
  items: PillItem[];
  testId?: string;
};

export function PillStrip({ items, testId }: PillStripProps) {
  if (!items.length) return null;
  return (
    <Group gap="xs" data-testid={testId}>
      {items.map((item) => (
        <Badge
          key={item.label}
          variant="light"
          color={item.color ?? "navy"}
          size="lg"
          radius="xl"
        >
          {item.label}
          {item.count !== undefined ? ` · ${item.count.toLocaleString()}` : ""}
        </Badge>
      ))}
    </Group>
  );
}
