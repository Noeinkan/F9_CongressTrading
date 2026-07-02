import { useCallback, useEffect, useState } from "react";
import type { SetURLSearchParams } from "react-router-dom";

import { useDebouncedValue } from "./useDebouncedValue";

type Params = {
  initial: string;
  delay?: number;
  paramName: string;
  searchParams: URLSearchParams;
  setSearchParams: SetURLSearchParams;
};

/**
 * Two-way bind a TextInput to a URL search param with debounced commit.
 *
 * - Local input state updates immediately so the user sees what they type.
 * - `committed` (returned) mirrors the URL value and is the value that
 *   should drive queries — it updates `delay` ms after the user stops
 *   typing.
 * - Pressing Enter commits instantly.
 *
 * Clearing the input removes the param from the URL (rather than
 * serializing an empty string).
 */
export function useUrlSearchParam({
  initial,
  delay = 300,
  paramName,
  searchParams,
  setSearchParams,
}: Params) {
  const urlValue = searchParams.get(paramName) ?? initial;
  const [draft, setDraft] = useState(urlValue);
  const debounced = useDebouncedValue(draft, delay);

  // Track which URL value the local draft was originally synced from so we
  // don't echo URL → draft → debounce → URL round-trips on every render.
  const [lastUrlValue, setLastUrlValue] = useState(urlValue);
  useEffect(() => {
    if (urlValue !== lastUrlValue) {
      setDraft(urlValue);
      setLastUrlValue(urlValue);
    }
  }, [urlValue, lastUrlValue]);

  const commit = useCallback(
    (value: string) => {
      const next = new URLSearchParams(searchParams);
      if (value) next.set(paramName, value);
      else next.delete(paramName);
      next.set("page", "1");
      setSearchParams(next);
      setLastUrlValue(value);
    },
    [paramName, searchParams, setSearchParams],
  );

  // Auto-commit when the debounced value changes (and differs from the URL).
  useEffect(() => {
    if (debounced !== urlValue) commit(debounced);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced]);

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      commit(draft);
    }
  };

  const clear = useCallback(() => {
    setDraft("");
    commit("");
  }, [commit]);

  return { draft, setDraft, onKeyDown, clear };
}
