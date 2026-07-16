import { initAll as initGovuk } from "govuk-frontend";
import { initAll as initMoj } from "@ministryofjustice/frontend";
import { initAll as initXGovuk } from "@x-govuk/govuk-prototype-components";
import AddAnotherAutocomplete from "./components/add-another-autocomplete/add-another-autocomplete.js";
import CopyButton from "./components/copy-button/copy-button.js";
import ModelTableFilter from "./components/model-table-filter/model-table-filter.js";

const App = {
  init: function () {
    initGovuk();
    initMoj();
    initXGovuk();

    // Initialize our components here
    AddAnotherAutocomplete.init();
    CopyButton.init();
    ModelTableFilter.init();
  },
};

export default App;
