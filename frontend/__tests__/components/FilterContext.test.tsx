import { render, screen, act, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import {
  DEFAULT_LOOKBACK,
  DEFAULT_QUARTERS,
  FilterProvider,
  parseLookbackParam,
  parseQuartersParam,
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

function renderConsumer(
  initial?: { lookback?: number | null; quarters?: string[] },
  initialEntries: string[] = ["/"],
) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <FilterProvider
        initialLookback={initial?.lookback === undefined ? undefined : initial.lookback}
        initialQuarters={
          (initial?.quarters as ("1" | "2" | "3" | "4")[] | undefined) ?? undefined
        }
      >
        <Consumer />
      </FilterProvider>
    </MemoryRouter>,
  );
}

describe("parseLookbackParam / parseQuartersParam", () => {
  it("parses lookback from URL tokens", () => {
    expect(parseLookbackParam(null)).toBe(DEFAULT_LOOKBACK);
    expect(parseLookbackParam("all")).toBeNull();
    expect(parseLookbackParam("5")).toBe(5);
    expect(parseLookbackParam("99")).toBe(DEFAULT_LOOKBACK);
  });

  it("parses quarters from URL tokens", () => {
    expect(parseQuartersParam(null)).toEqual(DEFAULT_QUARTERS);
    expect(parseQuartersParam("1,3")).toEqual(["1", "3"]);
  });
});

describe("FilterContext", () => {
  it("starts with default lookback and all quarters", () => {
    renderConsumer();
    expect(screen.getByTestId("lookback")).toHaveTextContent(String(DEFAULT_LOOKBACK));
    expect(screen.getByTestId("quarters")).toHaveTextContent(DEFAULT_QUARTERS.join(","));
  });

  it("respects initial values", () => {
    renderConsumer({ lookback: 3, quarters: ["1", "2"] });
    expect(screen.getByTestId("lookback")).toHaveTextContent("3");
    expect(screen.getByTestId("quarters")).toHaveTextContent("1,2");
  });

  it("reads lookback and quarters from the URL", () => {
    renderConsumer(undefined, ["/?lookback=5&quarters=1,2"]);
    expect(screen.getByTestId("lookback")).toHaveTextContent("5");
    expect(screen.getByTestId("quarters")).toHaveTextContent("1,2");
  });

  it("updates lookback via setLookback", async () => {
    renderConsumer();
    act(() => {
      screen.getByTestId("set-lookback").click();
    });
    await waitFor(() => {
      expect(screen.getByTestId("lookback")).toHaveTextContent("5");
    });
  });

  it("replaces quarters via setQuarters", async () => {
    renderConsumer();
    act(() => {
      screen.getByTestId("set-quarters").click();
    });
    await waitFor(() => {
      expect(screen.getByTestId("quarters")).toHaveTextContent("1,2");
    });
  });

  it("ignores unknown quarter values", () => {
    render(
      <MemoryRouter>
        <FilterProvider>
          <SanitizationProbe />
        </FilterProvider>
      </MemoryRouter>,
    );
    expect(screen.getByTestId("probe-quarters")).toHaveTextContent("1,2,3,4");
  });

  it("toggleQuarter adds and removes a quarter", async () => {
    renderConsumer({ quarters: ["1", "2", "3"] });
    act(() => {
      screen.getByTestId("toggle-q4").click();
    });
    await waitFor(() => {
      expect(screen.getByTestId("quarters")).toHaveTextContent("1,2,3,4");
    });
    act(() => {
      screen.getByTestId("toggle-q4").click();
    });
    await waitFor(() => {
      expect(screen.getByTestId("quarters")).toHaveTextContent("1,2,3");
    });
  });

  it("toggleQuarter refuses to remove the last remaining quarter", () => {
    render(
      <MemoryRouter>
        <FilterProvider initialQuarters={["1"]}>
          <RemoveLast />
        </FilterProvider>
      </MemoryRouter>,
    );
    act(() => {
      screen.getByTestId("remove-q1").click();
    });
    expect(screen.getByTestId("quarters-after")).toHaveTextContent("1");
  });

  it("reset returns to defaults", async () => {
    renderConsumer({ lookback: 5, quarters: ["1"] });
    act(() => {
      screen.getByTestId("reset").click();
    });
    await waitFor(() => {
      expect(screen.getByTestId("lookback")).toHaveTextContent(String(DEFAULT_LOOKBACK));
      expect(screen.getByTestId("quarters")).toHaveTextContent(DEFAULT_QUARTERS.join(","));
    });
  });

  it("supports all-time lookback via null", () => {
    render(
      <MemoryRouter>
        <FilterProvider initialLookback={null}>
          <Consumer />
        </FilterProvider>
      </MemoryRouter>,
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
