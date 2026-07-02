import { useEffect, useState } from "react";

/**
 * Returns a debounced mirror of `value`. Updates `delay` ms after the most
 * recent change. Used by Raw / Tickers search inputs so keystrokes don't
 * refire the query on every character; the caller typically keeps the
 * immediate `value` for the input field and uses the debounced copy for the
 * URL / query.
 */
export function useDebouncedValue<T>(value: T, delay = 250): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(value), delay);
    return () => window.clearTimeout(id);
  }, [value, delay]);

  return debounced;
}
