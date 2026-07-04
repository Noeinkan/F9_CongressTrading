import { ActionIcon, Card, Collapse, Stack, Text, Title } from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { useId, type KeyboardEvent, type ReactNode } from "react";

type ChartCardProps = {
  title: string;
  caption?: string;
  children: ReactNode;
  testId?: string;
  headerRight?: ReactNode;
  collapsible?: boolean;
  defaultCollapsed?: boolean;
};

function ChevronIcon({ opened }: { opened: boolean }) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      style={{
        transform: opened ? undefined : "rotate(-90deg)",
        transition: "transform 150ms",
      }}
      aria-hidden
    >
      <polyline points="6 9 12 15 18 9" />
    </svg>
  );
}

export function ChartCard({
  title,
  caption,
  children,
  testId,
  headerRight,
  collapsible = false,
  defaultCollapsed = false,
}: ChartCardProps) {
  const bodyId = useId();
  const [opened, { toggle }] = useDisclosure(!defaultCollapsed);

  const onHeaderKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (!collapsible) return;
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      toggle();
    }
  };

  const body = (
    <>
      {caption ? (
        <Text size="sm" c="dimmed">
          {caption}
        </Text>
      ) : null}
      {children}
    </>
  );

  return (
    <Card withBorder radius="md" padding="md" data-testid={testId}>
      <Stack gap="sm">
        <Stack gap={2}>
          <Card.Section inheritPadding py="xs">
            <div
              role={collapsible ? "button" : undefined}
              tabIndex={collapsible ? 0 : undefined}
              aria-expanded={collapsible ? opened : undefined}
              aria-controls={collapsible ? bodyId : undefined}
              onClick={collapsible ? toggle : undefined}
              onKeyDown={onHeaderKeyDown}
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                gap: 12,
                cursor: collapsible ? "pointer" : "default",
              }}
            >
              <Title order={4}>{title}</Title>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                {headerRight ? (
                  <div
                    onClick={(event) => event.stopPropagation()}
                    onKeyDown={(event) => event.stopPropagation()}
                  >
                    {headerRight}
                  </div>
                ) : null}
                {collapsible ? (
                  <ActionIcon variant="subtle" aria-hidden tabIndex={-1}>
                    <ChevronIcon opened={opened} />
                  </ActionIcon>
                ) : null}
              </div>
            </div>
          </Card.Section>
        </Stack>
        {collapsible ? (
          <Collapse in={opened}>
            <Stack gap="sm" id={bodyId}>
              {body}
            </Stack>
          </Collapse>
        ) : (
          body
        )}
      </Stack>
    </Card>
  );
}
