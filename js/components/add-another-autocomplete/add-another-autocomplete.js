import { initAll as initXGovuk } from "@x-govuk/govuk-prototype-components";
import EntraUserAutocomplete from "../entra-user-autocomplete/entra-user-autocomplete.js";

const AddAnotherAutocomplete = {
  init: function (scope = document) {
    const syncFormsetCount = function (container) {
      const form = container.closest("form");
      if (!form) {
        return;
      }

      const totalFormsField = form.querySelector('input[name$="-TOTAL_FORMS"]');
      if (!totalFormsField) {
        return;
      }

      const itemCount = container.querySelectorAll(
        ".moj-add-another__item",
      ).length;
      totalFormsField.value = String(itemCount);
    };

    const resetValidation = function (newItem) {
      newItem.querySelectorAll(".govuk-error-message").forEach((element) => {
        element.remove();
      });
      newItem
        .querySelectorAll(".govuk-form-group--error")
        .forEach((element) => {
          element.classList.remove("govuk-form-group--error");
        });
    };

    const resetSelectAutocomplete = function (newItem) {
      const select = newItem.querySelector(
        'select[data-module="autocomplete"]',
      );
      if (!select) {
        return;
      }

      // Remove cloned autocomplete UI so the new row starts empty.
      newItem
        .querySelectorAll(
          ".autocomplete__wrapper, .autocomplete__hint, .autocomplete__status",
        )
        .forEach((element) => element.remove());

      select.value = "";
      select.selectedIndex = 0;
      select.removeAttribute("aria-invalid");

      initXGovuk({ scope: newItem });
    };

    const resetEntraAutocomplete = function (newItem) {
      const mount = newItem.querySelector(
        '[data-module="entra-user-autocomplete"]',
      );
      if (!mount) {
        return;
      }

      // Drop cloned enhancement so init() can rebuild it from scratch.
      mount
        .querySelectorAll(
          ".autocomplete__wrapper, .autocomplete__hint, .autocomplete__status",
        )
        .forEach((element) => element.remove());
      delete mount.dataset.initialised;

      newItem
        .querySelectorAll(
          'input[type="hidden"][data-entra-user-id], input[type="hidden"][data-entra-user-email], input[type="hidden"][data-entra-user-name]',
        )
        .forEach((hidden) => {
          hidden.value = "";
        });

      EntraUserAutocomplete.init(newItem);
    };

    const addAnotherContainers = scope.querySelectorAll(
      '.moj-add-another[data-module="moj-add-another"]',
    );

    addAnotherContainers.forEach((container) => {
      syncFormsetCount(container);

      container.addEventListener("click", (event) => {
        const addButton = event.target.closest(".moj-add-another__add-button");
        const removeButton = event.target.closest(
          ".moj-add-another__remove-button",
        );

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

          resetValidation(newItem);
          resetSelectAutocomplete(newItem);
          resetEntraAutocomplete(newItem);
        });
      });
    });
  },
};

export default AddAnotherAutocomplete;
