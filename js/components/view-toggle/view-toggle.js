
const ViewToggle = {
  init() {
    document.querySelectorAll("[data-view-section]").forEach((section) => {
      const tableView = section.querySelector('[data-view="table"]');
      const chartView = section.querySelector('[data-view="chart"]');
      const radios = section.querySelectorAll('.app-view-toggle input[type="radio"]');

      radios.forEach((radio) => {
        radio.addEventListener("change", () => {
          const showChart = radio.value === "chart" && radio.checked;
          tableView.hidden = showChart;
          chartView.hidden = !showChart;

          if (showChart) {
            // Chart may have initialised at 0×0 while hidden; let ECharts know its
            // container now has real dimensions.
            section.dispatchEvent(new CustomEvent("usage-chart:visible", { bubbles: true }));
          }
        });
      });
    });
  },
};

export default ViewToggle;
