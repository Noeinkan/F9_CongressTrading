import { Avatar, Menu, UnstyledButton } from "@mantine/core";
import { useState } from "react";

import { useLogout, useSessionQuery } from "@/api/auth";

// The signed-in address is never rendered in the header (nor in its menu or
// aria-label): the header ends up in screenshots and screen shares.
export function UserMenu() {
  const session = useSessionQuery();
  const logout = useLogout();
  const [opened, setOpened] = useState(false);

  if (!session.data?.user || !session.data.auth_required) {
    return null;
  }

  return (
    <Menu opened={opened} onChange={setOpened} position="bottom-end" withinPortal>
      <Menu.Target>
        <UnstyledButton
          aria-label="Account menu"
          data-testid="user-menu-trigger"
          px="xs"
          py={4}
          style={{ borderRadius: 4 }}
        >
          <Avatar size="sm" color="navy" radius="xl" />
        </UnstyledButton>
      </Menu.Target>
      <Menu.Dropdown>
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
