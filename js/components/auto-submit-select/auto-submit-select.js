/**
 * Without JavaScript, the form's <noscript> submit button does the
 * same job on a click - browsers never render <noscript> content while JS is enabled,
 * so there's no need to hide that button here.
 **/
const AutoSubmitSelect = {
  init: function () {
    const forms = document.querySelectorAll(
      '[data-module="app-auto-submit-select"]',
    );

    forms.forEach((form) => {
      const controls = form.querySelectorAll("select, input[type='radio']");

      controls.forEach((control) => {
        control.addEventListener("change", () => {
          form.requestSubmit();
        });
      });
    });
  },
};

export default AutoSubmitSelect;
