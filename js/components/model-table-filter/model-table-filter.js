function enhance(wrapper) {
  const nameFilter = wrapper.querySelector('[data-model-filter="name"]');
  const providerFilter = wrapper.querySelector(
    '[data-model-filter="provider"]',
  );
  const rows = wrapper.querySelectorAll("[data-model-row]");
  const emptyMessage = wrapper.querySelector('[data-model-filter="empty"]');

  if (!nameFilter || !providerFilter || rows.length === 0) {
    return;
  }

  const applyFilters = () => {
    const nameQuery = nameFilter.value.trim().toLowerCase();
    const providerQuery = providerFilter.value;
    let visibleCount = 0;

    rows.forEach((row) => {
      const rowName = row.getAttribute("data-model-name") || "";
      const rowProvider = row.getAttribute("data-model-provider") || "";

      const matchesName = !nameQuery || rowName.includes(nameQuery);
      const matchesProvider = !providerQuery || rowProvider === providerQuery;
      const isVisible = matchesName && matchesProvider;

      row.hidden = !isVisible;
      if (isVisible) {
        visibleCount += 1;
      }
    });

    if (emptyMessage) {
      emptyMessage.hidden = visibleCount !== 0;
    }
  };

  nameFilter.addEventListener("input", applyFilters);
  providerFilter.addEventListener("change", applyFilters);
  applyFilters();
}

const ModelTableFilter = {
  init: function () {
    const wrappers = document.querySelectorAll(
      '[data-module="app-model-table-filter"]',
    );
    wrappers.forEach((wrapper) => enhance(wrapper));
  },
};

export default ModelTableFilter;
