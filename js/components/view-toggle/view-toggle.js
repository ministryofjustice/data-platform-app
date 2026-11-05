const ViewToggle = {
  init() {
    document.querySelectorAll("[data-view-section]").forEach((section) => {
      const tableView = section.querySelector('[data-view="table"]');
      const chartView = section.querySelector('[data-view="chart"]');
      if (!tableView || !chartView) return;
      const radios = section.querySelectorAll(
        '.app-view-toggle input[type="radio"]',
      );
      const metricTabs = Array.from(
        section.querySelectorAll("[data-chart-metric]"),
      );
      const metricPanels = section.querySelectorAll("[data-chart-panel]");
      const notifyChartVisible = () => {
        section.dispatchEvent(
          new CustomEvent("usage-chart:visible", { bubbles: true }),
        );
      };

      const selectMetric = (selectedTab) => {
        metricTabs.forEach((tab) => {
          const selected = tab === selectedTab;
          tab.setAttribute("aria-selected", String(selected));
          tab.tabIndex = selected ? 0 : -1;
        });
        metricPanels.forEach((panel) => {
          panel.hidden =
            panel.dataset.chartPanel !== selectedTab.dataset.chartMetric;
        });
        notifyChartVisible();
      };

      metricTabs.forEach((tab, index) => {
        tab.addEventListener("click", () => selectMetric(tab));
        tab.addEventListener("keydown", (event) => {
          let nextIndex;
          switch (event.key) {
            case "ArrowRight":
              nextIndex = (index + 1) % metricTabs.length;
              break;
            case "ArrowLeft":
              nextIndex = (index + metricTabs.length - 1) % metricTabs.length;
              break;
            case "Home":
              nextIndex = 0;
              break;
            case "End":
              nextIndex = metricTabs.length - 1;
              break;
            default:
              return;
          }
          event.preventDefault();
          const nextTab = metricTabs[nextIndex];
          selectMetric(nextTab);
          nextTab.focus();
        });
      });

      radios.forEach((radio) => {
        radio.addEventListener("change", () => {
          const showChart = radio.value === "chart" && radio.checked;
          tableView.hidden = showChart;
          chartView.hidden = !showChart;

          if (showChart) {
            notifyChartVisible();
          }
        });
      });
    });
  },
};

export default ViewToggle;
