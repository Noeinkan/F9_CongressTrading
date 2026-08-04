import ReactECharts from "echarts-for-react";

type EChartsChartProps = {
  option: Record<string, unknown> | null | undefined;
  height: number;
  testId?: string;
  onEvents?: Record<string, (params: unknown) => void>;
  notMerge?: boolean;
  lazyUpdate?: boolean;
};

export function EChartsChart({
  option,
  height,
  testId,
  onEvents,
  notMerge = false,
  lazyUpdate,
}: EChartsChartProps) {
  if (!option) return null;
  return (
    <div data-testid={testId}>
      <ReactECharts
        option={option}
        style={{ height, width: "100%" }}
        opts={{ renderer: "svg" }}
        onEvents={onEvents}
        notMerge={notMerge}
        lazyUpdate={lazyUpdate}
      />
    </div>
  );
}
