/**
 * Progressive enhancement for a native `<select multiple>`.
 *
 * Renders the selected options as removable tags and lets users add options
 * from a single-select dropdown. The underlying `<select multiple>` stays in
 * sync and remains the value the form submits, so the control still works when
 * JavaScript is unavailable.
 *
 * Enhances any element with `data-module="app-multi-select-tags"` that contains
 * a `<select multiple>`.
 */
function enhance(wrapper) {
  const nativeSelect = wrapper.querySelector("select[multiple]");
  if (!nativeSelect) {
    return;
  }

  const options = Array.from(nativeSelect.options).map((option) => ({
    value: option.value,
    label: option.textContent.trim(),
  }));

  const addSelect = document.createElement("select");
  addSelect.className = "govuk-select app-multi-select-tags__add";
  addSelect.setAttribute("aria-label", "Add a model");

  if (nativeSelect.id) {
    addSelect.id = `${nativeSelect.id}__add`;

    // Keep the visible enhanced control associated with the existing label.
    const label = wrapper.querySelector(`label[for="${nativeSelect.id}"]`);
    if (label) {
      label.setAttribute("for", addSelect.id);
    }
  }

  const control = document.createElement("div");
  control.className = "app-multi-select-tags__control";
  control.appendChild(addSelect);

  const list = document.createElement("ul");
  list.className = "moj-filter-tags app-multi-select-tags__list";
  list.setAttribute("aria-live", "polite");

  const optionFor = (value) =>
    Array.from(nativeSelect.options).find((option) => option.value === value);

  const isSelected = (value) => {
    const option = optionFor(value);
    return Boolean(option && option.selected);
  };

  const setSelected = (value, selected) => {
    const option = optionFor(value);
    if (option) {
      option.selected = selected;
    }
  };

  const rebuildAddOptions = () => {
    addSelect.innerHTML = "";

    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "Select a model";
    addSelect.appendChild(placeholder);

    options
      .filter((option) => !isSelected(option.value))
      .forEach((option) => {
        const element = document.createElement("option");
        element.value = option.value;
        element.textContent = option.label;
        addSelect.appendChild(element);
      });
  };

  const renderTags = () => {
    list.innerHTML = "";

    options
      .filter((option) => isSelected(option.value))
      .forEach((option) => {
        const item = document.createElement("li");

        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "moj-filter__tag app-multi-select-tags__remove";
        remove.setAttribute("aria-label", `Remove ${option.label}`);
        remove.textContent = option.label;
        remove.addEventListener("click", () => {
          setSelected(option.value, false);
          refresh();
        });

        item.appendChild(remove);
        list.appendChild(item);
      });
  };

  const refresh = () => {
    rebuildAddOptions();
    renderTags();
  };

  addSelect.addEventListener("change", () => {
    const { value } = addSelect;
    if (!value) {
      return;
    }
    setSelected(value, true);
    refresh();
  });

  nativeSelect.classList.add("app-multi-select-tags__native--enhanced");
  nativeSelect.setAttribute("aria-hidden", "true");
  nativeSelect.setAttribute("tabindex", "-1");

  // Insert both after the native select; the second insert lands directly
  // after it, so the final order is: native select, control, tag list.
  nativeSelect.insertAdjacentElement("afterend", list);
  nativeSelect.insertAdjacentElement("afterend", control);

  refresh();
}

const MultiSelectTags = {
  init: function () {
    const wrappers = document.querySelectorAll(
      '[data-module="app-multi-select-tags"]',
    );
    wrappers.forEach((wrapper) => enhance(wrapper));
  },
};

export default MultiSelectTags;
