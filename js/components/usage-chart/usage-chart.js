import * as echarts from "echarts/core";
import { BarChart, LineChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

echarts.use([
  BarChart,
  LineChart,
  GridComponent,
  TooltipComponent,
  CanvasRenderer,
]);

const UsageChart = {
  init() {
    const chartsByContainer = new Map();

    document.querySelectorAll("[data-chart-data-id]").forEach((container) => {
      const dataEl = document.getElementById(container.dataset.chartDataId);
      if (!dataEl) return;
      const {
        labels,
        values,
        horizontal,
        chart_type: chartType = "bar",
        category_axis_label: categoryAxisLabel,
        value_axis_label: valueAxisLabel,
      } = JSON.parse(dataEl.textContent);

      const chart = echarts.init(container);
      chart.setOption(
        horizontal
          ? {
              grid: { containLabel: true },
              xAxis: {
                type: "value",
                name: valueAxisLabel,
                nameLocation: "middle",
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
              series: [{ type: "bar", data: values }],
              tooltip: {
                trigger: "axis",
                valueFormatter: (value) => '$' + value.toFixed(2),
              },
            }
          : {
              xAxis: {
                type: "category",
                data: labels,
                name: categoryAxisLabel,
                nameLocation: "middle",
                nameGap: 30
              },
              yAxis: {
                type: "value",
                name: valueAxisLabel,
                nameLocation: "middle",
                nameGap: 40,
              },
              series: [
                {
                  type: chartType,
                  data: values,
                  smooth: chartType === "line",
                  areaStyle: chartType === "line" ? {} : undefined,
                },
              ],
              tooltip: {
                trigger: "axis",
                valueFormatter: (value) => '$' + value.toFixed(2),
              },
            },
      );
      chartsByContainer.set(container, chart);
    });

    const isVisible = (container) => container.offsetParent !== null;

    // Stops charts in other tabs from resizing
    window.addEventListener("resize", () => {
      chartsByContainer.forEach((chart, container) => {
        if (isVisible(container)) {
          chart.resize();
        }
      });
    });

    document.addEventListener("usage-chart:visible", (event) => {
      event.target
        .querySelectorAll("[data-chart-data-id]")
        .forEach((container) => {
          chartsByContainer.get(container)?.resize();
        });
    });
  },
};

export default UsageChart;
