import { initAll as initXGovuk } from "@x-govuk/govuk-prototype-components";

const AddAnotherAutocomplete = {
  init: function () {
    const syncFormsetCount = function (container) {
      const form = container.closest("form");
      if (!form) {
        return;
      }

      const totalFormsField = form.querySelector('input[name$="-TOTAL_FORMS"]');
      if (!totalFormsField) {
        return;
      }

      const itemCount = container.querySelectorAll(".moj-add-another__item").length;
      totalFormsField.value = String(itemCount);
    };

    const addAnotherContainers = document.querySelectorAll(
      '.moj-add-another[data-module="moj-add-another"]'
    );

    addAnotherContainers.forEach((container) => {
      syncFormsetCount(container);

      container.addEventListener("click", (event) => {
        const addButton = event.target.closest(".moj-add-another__add-button");
        const removeButton = event.target.closest(".moj-add-another__remove-button");

        if (!addButton && !removeButton) {
          return;
        }

        // Wait for MOJ add-another to apply DOM changes.
        window.requestAnimationFrame(() => {
          syncFormsetCount(container);

          if (removeButton) {
            return;
          }

          const items = container.querySelectorAll(".moj-add-another__item");
          const newItem = items[items.length - 1];
          if (!newItem) {
            return;
          }

          const select = newItem.querySelector('select[data-module="autocomplete"]');
          if (!select) {
            return;
          }

          // Remove cloned autocomplete UI so the new row starts empty.
          newItem
            .querySelectorAll(
              ".autocomplete__wrapper, .autocomplete__hint, .autocomplete__status"
            )
            .forEach((element) => element.remove());

          select.value = "";
          select.selectedIndex = 0;

          initXGovuk({ scope: newItem });
        });
      });
    });
  },
};

export default AddAnotherAutocomplete;
