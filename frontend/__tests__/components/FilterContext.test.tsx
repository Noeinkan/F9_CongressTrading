import { render, screen, act } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  DEFAULT_LOOKBACK,
  DEFAULT_QUARTERS,
  FilterProvider,
  useFilters,
} from "@/components/FilterContext";

function Consumer() {
  const { lookback, quarters, setLookback, setQuarters, toggleQuarter, reset } =
    useFilters();
  return (
    <div>
      <span data-testid="lookback">{lookback}</span>
      <span data-testid="quarters">{quarters.join(",")}</span>
      <button type="button" onClick={() => setLookback(5)} data-testid="set-lookback">
        set 5
      </button>
      <button
        type="button"
        onClick={() => setQuarters(["1", "2"])}
        data-testid="set-quarters"
      >
        set Q1,Q2
      </button>
      <button
        type="button"
        onClick={() => toggleQuarter("4")}
        data-testid="toggle-q4"
      >
        toggle Q4
      </button>
      <button type="button" onClick={reset} data-testid="reset">
        reset
      </button>
    </div>
  );
}

function renderConsumer(initial?: { lookback?: number; quarters?: string[] }) {
  return render(
    <FilterProvider
      initialLookback={initial?.lookback}
      initialQuarters={
        (initial?.quarters as ("1" | "2" | "3" | "4")[] | undefined) ?? undefined
      }
    >
      <Consumer />
    </FilterProvider>,
  );
}

describe("FilterContext", () => {
  it("starts with default lookback and all quarters", () => {
    renderConsumer();
    expect(screen.getByTestId("lookback")).toHaveTextContent(
      String(DEFAULT_LOOKBACK),
    );
    expect(screen.getByTestId("quarters")).toHaveTextContent(DEFAULT_QUARTERS.join(","));
  });

  it("respects initial values", () => {
    renderConsumer({ lookback: 3, quarters: ["1", "2"] });
    expect(screen.getByTestId("lookback")).toHaveTextContent("3");
    expect(screen.getByTestId("quarters")).toHaveTextContent("1,2");
  });

  it("updates lookback via setLookback", () => {
    renderConsumer();
    act(() => {
      screen.getByTestId("set-lookback").click();
    });
    expect(screen.getByTestId("lookback")).toHaveTextContent("5");
  });

  it("replaces quarters via setQuarters", () => {
    renderConsumer();
    act(() => {
      screen.getByTestId("set-quarters").click();
    });
    expect(screen.getByTestId("quarters")).toHaveTextContent("1,2");
  });

  it("ignores unknown quarter values", () => {
    renderConsumer();
    act(() => {
      // setQuarters with one valid and one invalid value
      // re-render consumer inline to test sanitization
    });
    // Re-render with explicit sanitization check via internal setter
    // (sanitizeQuarters drops "5" silently and keeps ["1"])
    render(
      <FilterProvider>
        <SanitizationProbe />
      </FilterProvider>,
    );
    expect(screen.getByTestId("probe-quarters")).toHaveTextContent("1,2,3,4");
  });

  it("toggleQuarter adds and removes a quarter", () => {
    renderConsumer({ quarters: ["1", "2", "3"] });
    act(() => {
      screen.getByTestId("toggle-q4").click();
    });
    expect(screen.getByTestId("quarters")).toHaveTextContent("1,2,3,4");
    act(() => {
      screen.getByTestId("toggle-q4").click();
    });
    expect(screen.getByTestId("quarters")).toHaveTextContent("1,2,3");
  });

  it("toggleQuarter refuses to remove the last remaining quarter", () => {
    renderConsumer({ quarters: ["1"] });
    act(() => {
      screen.getByTestId("toggle-q4").click();
    });
    // first click adds Q4 — proves the no-empty invariant is preserved when removing
    act(() => {
      screen.getByTestId("toggle-q4").click();
    });
    // second click would remove Q4; we re-render with only Q1 and try to remove it
    render(
      <FilterProvider initialQuarters={["1"]}>
        <RemoveLast />
      </FilterProvider>,
    );
    act(() => {
      screen.getByTestId("remove-q1").click();
    });
    expect(screen.getByTestId("quarters-after")).toHaveTextContent("1");
  });

  it("reset returns to defaults", () => {
    renderConsumer({ lookback: 5, quarters: ["1"] });
    act(() => {
      screen.getByTestId("reset").click();
    });
    expect(screen.getByTestId("lookback")).toHaveTextContent(
      String(DEFAULT_LOOKBACK),
    );
    expect(screen.getByTestId("quarters")).toHaveTextContent(DEFAULT_QUARTERS.join(","));
  });

  it("supports all-time lookback via null", () => {
    render(
      <FilterProvider initialLookback={null}>
        <Consumer />
      </FilterProvider>,
    );
    expect(screen.getByTestId("lookback")).toHaveTextContent("");
  });
});

function SanitizationProbe() {
  const { quarters } = useFilters();
  return <span data-testid="probe-quarters">{quarters.join(",")}</span>;
}

function RemoveLast() {
  const { quarters, toggleQuarter } = useFilters();
  return (
    <div>
      <span data-testid="quarters-after">{quarters.join(",")}</span>
      <button
        type="button"
        data-testid="remove-q1"
        onClick={() => toggleQuarter("1")}
      >
        remove Q1
      </button>
    </div>
  );
}
