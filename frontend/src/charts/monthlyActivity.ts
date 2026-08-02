import { formatCurrency, formatDisclosedRange } from "@/utils/format";

export type MonthlyActivityRow = {
  month: string | null;
  transactions: number;
  buy?: number;
  sell?: number;
  other?: number;
  amount_low: number;
  amount_high: number;
};

/** STOCK Act disclosures can lag ~30–45 days; shade recent months accordingly. */
export const FILING_LAG_DAYS = 45;

export function monthKey(raw: string | null | undefined): string {
  if (!raw) return "";
  return String(raw).slice(0, 7);
}

/**
 * A month is likely incomplete when its last calendar day is still inside the
 * filing-lag window (or the month is current/future relative to ``now``).
 */
export function isMonthLikelyIncomplete(
  ym: string,
  now: Date = new Date(),
  lagDays: number = FILING_LAG_DAYS,
): boolean {
  if (!/^\d{4}-\d{2}$/.test(ym)) return false;
  const year = Number(ym.slice(0, 4));
  const monthIndex = Number(ym.slice(5, 7)) - 1;
  if (!Number.isFinite(year) || !Number.isFinite(monthIndex)) return false;
  // Last instant of the month in local time.
  const monthEnd = new Date(year, monthIndex + 1, 0, 23, 59, 59, 999);
  const lagCutoff = new Date(now);
  lagCutoff.setHours(0, 0, 0, 0);
  lagCutoff.setDate(lagCutoff.getDate() - lagDays);
  return monthEnd >= lagCutoff;
}

export function incompleteMonthKeys(
  months: string[],
  now: Date = new Date(),
  lagDays: number = FILING_LAG_DAYS,
): string[] {
  return months.filter((m) => m && isMonthLikelyIncomplete(m, now, lagDays));
}

function asCount(value: unknown): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}

type TooltipParam = {
  seriesName?: string;
  value?: number | string;
  marker?: string;
  axisValue?: string;
  dataIndex?: number;
};

export function buildMonthlyActivityOption(
  rows: MonthlyActivityRow[],
  now: Date = new Date(),
): Record<string, unknown> {
  const months = rows.map((r) => monthKey(r.month));
  const buys = rows.map((r) => asCount(r.buy));
  const sells = rows.map((r) => asCount(r.sell));
  const others = rows.map((r) => {
    // Back-compat: older payloads only had a total count (no buy/sell/other).
    if (r.buy == null && r.sell == null && r.other == null) {
      return asCount(r.transactions);
    }
    return asCount(r.other);
  });
  const amountHigh = rows.map((r) => asCount(r.amount_high));
  const amountLow = rows.map((r) => asCount(r.amount_low));

  const incomplete = incompleteMonthKeys(months, now);
  const markArea =
    incomplete.length > 0
      ? {
          silent: true,
          itemStyle: { color: "rgba(148, 163, 184, 0.16)" },
          label: {
            show: true,
            position: "insideTop",
            formatter: "Filing lag",
            color: "#64748b",
            fontSize: 11,
          },
          data: [[{ xAxis: incomplete[0] }, { xAxis: incomplete[incomplete.length - 1] }]],
        }
      : undefined;

  return {
    grid: { left: 52, right: 56, top: 28, bottom: 56 },
    legend: {
      bottom: 0,
      data: ["Buy", "Sell", "Other", "Disclosed $ high"],
    },
    xAxis: { type: "category", data: months },
    yAxis: [
      { type: "value", name: "Trades", nameGap: 10 },
      {
        type: "value",
        name: "Disclosed $",
        nameGap: 10,
        axisLabel: {
          formatter: (v: number) => formatCurrency(v),
        },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: "Buy",
        type: "bar",
        stack: "side",
        data: buys,
        itemStyle: { color: "#2f6f4e" },
        markArea,
      },
      {
        name: "Sell",
        type: "bar",
        stack: "side",
        data: sells,
        itemStyle: { color: "#a64b2a" },
      },
      {
        name: "Other",
        type: "bar",
        stack: "side",
        data: others,
        itemStyle: { color: "#94a3b8" },
      },
      {
        name: "Disclosed $ high",
        type: "line",
        yAxisIndex: 1,
        data: amountHigh,
        smooth: true,
        symbol: "circle",
        symbolSize: 6,
        lineStyle: { color: "#c6922b", width: 2 },
        itemStyle: { color: "#c6922b" },
      },
    ],
    tooltip: {
      trigger: "axis",
      formatter: (params: TooltipParam | TooltipParam[]) => {
        const list = Array.isArray(params) ? params : [params];
        const idx = list[0]?.dataIndex ?? 0;
        const month = months[idx] ?? list[0]?.axisValue ?? "";
        const range = formatDisclosedRange(amountLow[idx] ?? 0, amountHigh[idx] ?? 0);
        const lagNote = incomplete.includes(month)
          ? `<div style="color:#64748b;margin-top:4px">Likely incomplete (≤${FILING_LAG_DAYS}d filing lag)</div>`
          : "";
        const lines = list
          .map((p) => {
            const raw = Number(p.value ?? 0);
            const display =
              p.seriesName === "Disclosed $ high" ? formatCurrency(raw) : String(raw);
            return `${p.marker ?? ""}${p.seriesName ?? ""}: <b>${display}</b>`;
          })
          .join("<br/>");
        return `<div><b>${month}</b><br/>${lines}<br/>Range: ${range}${lagNote}</div>`;
      },
    },
  };
}
