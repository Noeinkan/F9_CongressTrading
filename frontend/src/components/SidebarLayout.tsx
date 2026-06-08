import { AppShell as MantineAppShell, ScrollArea } from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { useEffect } from "react";
import { Outlet, useLocation } from "react-router-dom";

import { useIsMobile } from "@/hooks/useMediaQuery";

import { SidebarFilters } from "./SidebarFilters";
import { TopBar } from "./TopBar";

/** Persistent shell: top bar with brand/nav/user, collapsible left sidebar with global filters. */
export function SidebarLayout() {
  const isMobile = useIsMobile();
  const [mobileOpened, mobileHandlers] = useDisclosure(false);
  const [desktopOpened, desktopHandlers] = useDisclosure(true);
  const location = useLocation();

  // Auto-close the mobile drawer on every route change.
  useEffect(() => {
    if (isMobile && mobileOpened) {
      mobileHandlers.close();
    }
  }, [location.pathname, isMobile, mobileOpened, mobileHandlers]);

  const navbarOpen = isMobile ? mobileOpened : desktopOpened;
  const onToggle = () => {
    if (isMobile) {
      mobileHandlers.toggle();
    } else {
      desktopHandlers.toggle();
    }
  };

  return (
    <MantineAppShell
      header={{ height: 64 }}
      navbar={{
        width: 260,
        breakpoint: "sm",
        collapsed: { mobile: !mobileOpened, desktop: !desktopOpened },
      }}
      padding="md"
    >
      <MantineAppShell.Header>
        <TopBar onToggleNavbar={onToggle} navbarOpen={navbarOpen} />
      </MantineAppShell.Header>
      <MantineAppShell.Navbar>
        <ScrollArea h="100%" type="auto" offsetScrollbars>
          <SidebarFilters />
        </ScrollArea>
      </MantineAppShell.Navbar>
      <MantineAppShell.Main>
        <Outlet />
      </MantineAppShell.Main>
    </MantineAppShell>
  );
}
