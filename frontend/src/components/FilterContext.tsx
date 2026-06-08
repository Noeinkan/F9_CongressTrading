import {

  createContext,

  useCallback,

  useContext,

  useMemo,

  useState,

  type ReactNode,

} from "react";



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



type FilterProviderProps = {

  children: ReactNode;

  initialLookback?: LookbackValue;

  initialQuarters?: QuarterValue[];

};



export function FilterProvider({

  children,

  initialLookback = DEFAULT_LOOKBACK,

  initialQuarters = DEFAULT_QUARTERS,

}: FilterProviderProps) {

  const [lookback, setLookbackState] = useState<LookbackValue>(initialLookback);

  const [quarters, setQuartersState] = useState<QuarterValue[]>(initialQuarters);



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


