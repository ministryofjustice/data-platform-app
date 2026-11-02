import * as echarts from "echarts/core";
import { BarChart, LineChart } from "echarts/charts";
import {
  GridComponent,
  LegendComponent,
  TooltipComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

echarts.use([
  BarChart,
  LineChart,
  GridComponent,
  LegendComponent,
  TooltipComponent,
  CanvasRenderer,
]);

const UsageChart = {
  init() {
    const chartsByContainer = new Map();

    const showChart = (container) => {
      if (!container.clientWidth || !container.clientHeight) return;
      const existingChart = chartsByContainer.get(container);
      if (existingChart) {
        existingChart.resize();
        return;
      }
      const dataEl = document.getElementById(container.dataset.chartDataId);
      if (!dataEl) return;
      const {
        labels,
        values,
        series: namedSeries,
        horizontal,
        chart_type: chartType = "bar",
        category_axis_label: categoryAxisLabel,
        value_axis_label: valueAxisLabel,
        value_format: valueFormat = "currency",
      } = JSON.parse(dataEl.textContent);
      const isCount = valueFormat === "count";
      const countFormatter = new Intl.NumberFormat("en-GB", {
        maximumFractionDigits: 0,
      });
      const valueFormatter = (value) =>
        isCount ? countFormatter.format(value) : "$" + value.toFixed(2);
      const valueAxis = {
        type: "value",
        name: valueAxisLabel,
        nameLocation: "middle",
        minInterval: 1,
        axisLabel: {
          show: true,
          formatter: (value) =>
            isCount ? countFormatter.format(value) : `$${value.toFixed(0)}`,
        },
      };
      const multipleSeries = namedSeries?.length > 1;
      const seriesOptions = {
        series: (namedSeries ?? [{ values }]).map((series, index) => ({
          name: series.name,
          type: horizontal ? "bar" : chartType,
          data: series.values,
          smooth: !multipleSeries && chartType === "line",
          areaStyle:
            !multipleSeries && !horizontal && chartType === "line"
              ? {}
              : undefined,
          symbol: multipleSeries
            ? index === 0
              ? "circle"
              : "triangle"
            : undefined,
          lineStyle: multipleSeries
            ? { type: index === 0 ? "solid" : "dashed" }
            : undefined,
        })),
        tooltip: { trigger: "axis", valueFormatter },
        ...(multipleSeries
          ? {
              legend: { top: 0, type: "scroll" },
            }
          : {}),
        color: multipleSeries ? ["#1d70b8", "#4b9b7d"] : ["#1d70b8"],
      };

      const chart = echarts.init(container);
      chart.setOption(
        horizontal
          ? {
              ...seriesOptions,
              grid: {
                containLabel: true,
                top: multipleSeries ? 45 : undefined,
                bottom: multipleSeries ? 60 : undefined,
              },
              xAxis: {
                ...valueAxis,
                nameGap: 30,
              },
              yAxis: {
                type: "category",
                data: labels,
                name: categoryAxisLabel,
                nameTextStyle: {
                  align: "left",
                  padding: [0, 0, 0, -80],
                },
              },
            }
          : {
              ...seriesOptions,
              grid: multipleSeries
                ? {
                    containLabel: true,
                    top: 45,
                    left: 65,
                    right: 20,
                    bottom: 60,
                  }
                : undefined,
              xAxis: {
                type: "category",
                data: labels,
                name: categoryAxisLabel,
                nameLocation: "middle",
                nameGap: 30,
              },
              yAxis: {
                ...valueAxis,
                nameGap: multipleSeries ? 60 : 40,
              },
            },
      );
      chartsByContainer.set(container, chart);
    };

    const resizeObserver = new ResizeObserver((entries) => {
      entries.forEach(({ target }) => showChart(target));
    });
    document.querySelectorAll("[data-chart-data-id]").forEach((container) => {
      resizeObserver.observe(container);
      showChart(container);
    });

    window.addEventListener("resize", () => {
      for (const container of chartsByContainer.keys()) {
        showChart(container);
      }
    });

    document.addEventListener("usage-chart:visible", (event) => {
      event.target
        .querySelectorAll("[data-chart-data-id]")
        .forEach((container) => {
          showChart(container);
        });
    });
  },
};

export default UsageChart;
