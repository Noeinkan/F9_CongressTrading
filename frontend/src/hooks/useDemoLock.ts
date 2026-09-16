import { useCallback } from "react";

import { emitDemoRefusal } from "@/api/client";
import { useDemoStatus } from "@/api/demo";

/**
 * Whether one named feature (`csv_export`, `review_actions`, …) is locked in
 * the running demo, and a way to raise the same wall the server would raise
 * if the request had actually gone out.
 *
 * Locked controls stay visible and clickable in the demo — hiding or
 * disabling them makes the product look smaller than it is. `open()` lets the
 * click handler short-circuit before doing anything (an `<a download>` that
 * must never navigate, a mutation that would only come back 403), while
 * still funnelling through the one `DemoWall` that a real refusal would hit.
 */
export function useDemoLock(feature: string): {
  locked: boolean;
  message?: string;
  label?: string;
  open: () => void;
} {
  const { data } = useDemoStatus();
  const isDemo = data?.enabled ?? false;
  const entry = data?.locked?.find((item) => item.feature === feature);
  const locked = isDemo && Boolean(entry);

  const open = useCallback(() => {
    if (!entry) return;
    emitDemoRefusal({ code: "DEMO_LOCKED", feature: entry.feature, detail: entry.message });
  }, [entry]);

  return { locked, message: entry?.message, label: entry?.label, open };
}
