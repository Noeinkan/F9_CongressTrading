import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useSearchParams } from "react-router-dom";

/** Lookback choices mirrored from the Streamlit `dashboard_shared.filters._LOOKBACK_OPTIONS`. */
export const LOOKBACK_OPTIONS = [
  { value: null, label: "All time" },
  { value: 1, label: "1 year" },
  { value: 2, label: "2 years" },
  { value: 3, label: "3 years" },
  { value: 5, label: "5 years" },
  { value: 10, label: "10 years" },
] as const;

export type LookbackValue = number | null;

export const QUARTER_VALUES = ["1", "2", "3", "4"] as const;
export type QuarterValue = (typeof QUARTER_VALUES)[number];

export const DEFAULT_LOOKBACK: LookbackValue = 1;
export const DEFAULT_QUARTERS: QuarterValue[] = [...QUARTER_VALUES];

const LOOKBACK_YEARS = new Set([1, 2, 3, 5, 10]);

type FilterState = {
  lookback: LookbackValue;
  quarters: QuarterValue[];
};

type FilterContextValue = FilterState & {
  setLookback: (value: LookbackValue) => void;
  setQuarters: (values: QuarterValue[]) => void;
  toggleQuarter: (value: QuarterValue) => void;
  reset: () => void;
};

const FilterContext = createContext<FilterContextValue | null>(null);

function isQuarter(value: string): value is QuarterValue {
  return (QUARTER_VALUES as readonly string[]).includes(value);
}

function sanitizeQuarters(values: string[]): QuarterValue[] {
  const seen = new Set<QuarterValue>();
  const out: QuarterValue[] = [];
  for (const v of values) {
    if (isQuarter(v) && !seen.has(v)) {
      seen.add(v);
      out.push(v);
    }
  }
  return out.length > 0 ? out : [...DEFAULT_QUARTERS];
}

/** Parse `?lookback=` — missing → fallback; `all` → null (all time). */
export function parseLookbackParam(
  raw: string | null,
  fallback: LookbackValue = DEFAULT_LOOKBACK,
): LookbackValue {
  if (raw === null || raw === "") return fallback;
  if (raw === "all") return null;
  const n = Number(raw);
  if (LOOKBACK_YEARS.has(n)) return n;
  return fallback;
}

/** Parse `?quarters=` — missing → fallback; comma-separated 1–4. */
export function parseQuartersParam(
  raw: string | null,
  fallback: QuarterValue[] = DEFAULT_QUARTERS,
): QuarterValue[] {
  if (raw === null || raw === "") return [...fallback];
  return sanitizeQuarters(raw.split(","));
}

function writePeriodParams(
  params: URLSearchParams,
  lookback: LookbackValue,
  quarters: QuarterValue[],
): void {
  if (lookback === DEFAULT_LOOKBACK) {
    params.delete("lookback");
  } else if (lookback === null) {
    params.set("lookback", "all");
  } else {
    params.set("lookback", String(lookback));
  }

  const allQuarters =
    quarters.length === DEFAULT_QUARTERS.length &&
    DEFAULT_QUARTERS.every((q) => quarters.includes(q));
  if (allQuarters) {
    params.delete("quarters");
  } else {
    params.set("quarters", [...quarters].sort().join(","));
  }
}

type FilterProviderProps = {
  children: ReactNode;
  initialLookback?: LookbackValue;
  initialQuarters?: QuarterValue[];
};

/**
 * Period filters shared across dashboard pages.
 * Must render inside a React Router tree (`useSearchParams`).
 * Persists `lookback` / `quarters` in the URL for refresh/share.
 */
export function FilterProvider({
  children,
  initialLookback = DEFAULT_LOOKBACK,
  initialQuarters = DEFAULT_QUARTERS,
}: FilterProviderProps) {
  const [searchParams, setSearchParams] = useSearchParams();

  const [lookback, setLookbackState] = useState<LookbackValue>(() =>
    parseLookbackParam(searchParams.get("lookback"), initialLookback),
  );
  const [quarters, setQuartersState] = useState<QuarterValue[]>(() =>
    parseQuartersParam(searchParams.get("quarters"), initialQuarters),
  );

  // Keep React state as source of truth across in-app nav that drops query
  // params; re-write period params onto the current URL.
  const skipNextUrlRead = useRef(false);

  useEffect(() => {
    skipNextUrlRead.current = true;
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        writePeriodParams(next, lookback, quarters);
        if (next.toString() === prev.toString()) return prev;
        return next;
      },
      { replace: true },
    );
  }, [lookback, quarters, setSearchParams]);

  // Browser back/forward (or shared links) → sync state from URL.
  useEffect(() => {
    if (skipNextUrlRead.current) {
      skipNextUrlRead.current = false;
      return;
    }
    const nextLookback = parseLookbackParam(searchParams.get("lookback"), DEFAULT_LOOKBACK);
    const nextQuarters = parseQuartersParam(searchParams.get("quarters"), DEFAULT_QUARTERS);
    setLookbackState((prev) => (prev === nextLookback ? prev : nextLookback));
    setQuartersState((prev) => {
      const same =
        prev.length === nextQuarters.length && prev.every((q, i) => q === nextQuarters[i]);
      return same ? prev : nextQuarters;
    });
  }, [searchParams]);

  const setLookback = useCallback((value: LookbackValue) => {
    setLookbackState(value);
  }, []);

  const setQuarters = useCallback((values: string[]) => {
    setQuartersState(sanitizeQuarters(values));
  }, []);

  const toggleQuarter = useCallback((value: QuarterValue) => {
    setQuartersState((prev) => {
      if (prev.includes(value)) {
        const next = prev.filter((q) => q !== value);
        return next.length > 0 ? next : prev;
      }
      return [...prev, value].sort();
    });
  }, []);

  const reset = useCallback(() => {
    setLookbackState(DEFAULT_LOOKBACK);
    setQuartersState(DEFAULT_QUARTERS);
  }, []);

  const value = useMemo<FilterContextValue>(
    () => ({ lookback, quarters, setLookback, setQuarters, toggleQuarter, reset }),
    [lookback, quarters, setLookback, setQuarters, toggleQuarter, reset],
  );

  return <FilterContext.Provider value={value}>{children}</FilterContext.Provider>;
}

export function useFilters(): FilterContextValue {
  const ctx = useContext(FilterContext);
  if (!ctx) {
    throw new Error("useFilters must be used inside <FilterProvider>");
  }
  return ctx;
}
