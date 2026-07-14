import { initAll as initGovuk } from "govuk-frontend";
import { initAll as initMoj } from "@ministryofjustice/frontend";
import { initAll as initXGovuk } from "@x-govuk/govuk-prototype-components";
import AddAnotherAutocomplete from "./components/add-another-autocomplete/add-another-autocomplete.js";
import CopyButton from "./components/copy-button/copy-button.js";
import MultiSelectTags from "./components/multi-select-tags/multi-select-tags.js";

const App = {
  init: function () {
    initGovuk();
    initMoj();
    initXGovuk();

    // Initialize our components here
    AddAnotherAutocomplete.init();
    CopyButton.init();
    MultiSelectTags.init();
  },
};

export default App;
