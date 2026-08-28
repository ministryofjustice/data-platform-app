import { initAll as initGovuk } from "govuk-frontend";
import { initAll as initMoj } from "@ministryofjustice/frontend";
import { initAll as initXGovuk } from "@x-govuk/govuk-prototype-components";
import htmx from "htmx.org";
import AddAnotherAutocomplete from "./components/add-another-autocomplete/add-another-autocomplete.js";
import AutoSubmitSelect from "./components/auto-submit-select/auto-submit-select.js";
import CopyButton from "./components/copy-button/copy-button.js";
import EntraUserAutocomplete from "./components/entra-user-autocomplete/entra-user-autocomplete.js";
import UsageChart from "./components/usage-chart/usage-chart.js";
import ViewToggle from "./components/view-toggle/view-toggle.js";

window.htmx = htmx;

// Re-run the scope-aware framework initialisers against a fragment that HTMX has
// just inserted, so any GOV.UK or MOJ components inside it become interactive.
// Both initialisers accept a scope element and only touch components within it.
// NOTE: our own components (AddAnotherAutocomplete, AutoSubmitSelect, CopyButton) and
// x-govuk are intentionally excluded. They scan the whole document and attach listeners
// without guarding against re-initialisation, so re-running them per swap would
// double-bind handlers. Don't rely on those inside HTMX-swapped fragments until
// they are made scope-aware and idempotent.
function reinitialiseSwappedContent(scope) {
  initGovuk(scope);
  initMoj(scope);
  EntraUserAutocomplete.init(scope);
}

let initialised = false;

const App = {
  init: function () {
    if (initialised) {
      return;
    }

    initialised = true;

    initGovuk();
    initMoj();
    initXGovuk();

    AddAnotherAutocomplete.init();
    AutoSubmitSelect.init();
    CopyButton.init();
    EntraUserAutocomplete.init();
    UsageChart.init();
    ViewToggle.init();

    document.body.addEventListener("htmx:afterSwap", function (event) {
      reinitialiseSwappedContent(event.detail.target);
    });
    document.body.addEventListener("htmx:oobAfterSwap", function (event) {
      reinitialiseSwappedContent(event.detail.target);
    });
  },
};

export default App;
