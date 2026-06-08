import { Avatar, Group, Menu, Text, UnstyledButton } from "@mantine/core";
import { useState } from "react";

import { useLogout, useSessionQuery } from "@/api/auth";

export function UserMenu() {
  const session = useSessionQuery();
  const logout = useLogout();
  const [opened, setOpened] = useState(false);

  if (!session.data?.user) {
    return null;
  }

  const user = session.data.user;

  if (!session.data.auth_required) {
    return (
      <Text size="sm" c="dimmed">
        {user}
      </Text>
    );
  }

  return (
    <Menu opened={opened} onChange={setOpened} position="bottom-end" withinPortal>
      <Menu.Target>
        <UnstyledButton
          aria-label={`Account menu for ${user}`}
          data-testid="user-menu-trigger"
          px="xs"
          py={4}
          style={{ borderRadius: 4 }}
        >
          <Group gap="xs" wrap="nowrap">
            <Avatar size="sm" color="navy" radius="xl">
              {user.slice(0, 1).toUpperCase()}
            </Avatar>
            <Text size="sm" fw={500} visibleFrom="sm">
              {user}
            </Text>
          </Group>
        </UnstyledButton>
      </Menu.Target>
      <Menu.Dropdown>
        <Menu.Label>Signed in as {user}</Menu.Label>
        <Menu.Divider />
        <Menu.Item
          color="red"
          disabled={logout.isPending}
          onClick={() => logout.mutate()}
        >
          {logout.isPending ? "Logging out…" : "Log out"}
        </Menu.Item>
      </Menu.Dropdown>
    </Menu>
  );
}
