import { AppShell as MantineAppShell } from "@mantine/core";
import { Outlet } from "react-router-dom";

import { DemoBanner } from "./DemoBanner";
import { DemoWall } from "./DemoWall";
import { FilterProvider } from "./FilterContext";
import { TopBar } from "./TopBar";

/**
 * Persistent shell: top bar with brand, nav, refresh and user menu.
 *
 * There is no left sidebar any more. The period slice (`FilterProvider`) still
 * wraps every page and is read from `?lookback=` / `?quarters=`, so shared
 * links keep working; without them pages show the default 1-year window.
 */
export function SidebarLayout() {
  return (
    <FilterProvider>
      <DemoWall />
      <MantineAppShell header={{ height: 64 }} padding="md">
        <MantineAppShell.Header>
          <TopBar />
        </MantineAppShell.Header>
        <MantineAppShell.Main>
          <DemoBanner />
          <Outlet />
        </MantineAppShell.Main>
      </MantineAppShell>
    </FilterProvider>
  );
}
