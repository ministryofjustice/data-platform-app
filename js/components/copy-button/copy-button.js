/**
 * @param {string} textElementId - Id of the element whose text will be copied
 * @param {string} copyElementId - Id of the copy button element
 * @param {string} screenReaderAlertText - text that will be added into live region for screen reader users
 * @param {string} originalCopyText - original text of copy button element
 **/
function copyText(
  textElementId,
  copyElementId,
  screenReaderAlertText,
  originalCopyText = "Copy",
) {
  let textElement = document.querySelector(textElementId);
  let copyElement = document.querySelector(copyElementId);
  let screenReaderAlert = document.getElementById("copy-alert");

  if (textElement && copyElement) {
    copyElement.addEventListener("click", (e) => {
      e.preventDefault();

      let text = textElement.textContent.trim();
      window.navigator.clipboard.writeText(text);
      screenReaderAlert.textContent = screenReaderAlertText;
      copyElement.classList.add("disable-click");
      copyElement.textContent = "Copied";

      setTimeout(() => {
        screenReaderAlert.textContent = "";
        copyElement.classList.remove("disable-click");
        copyElement.textContent = originalCopyText;
      }, 4000);

      copyElement.blur();
      return true;
    });
  }
}

const CopyButton = {
  init: function () {
    // Find all buttons with data-module="copy-button"
    const buttons = document.querySelectorAll('[data-module="copy-button"]');

    buttons.forEach((button) => {
      const textSelector = button.dataset.textSelector;
      const successMessage = button.dataset.successMessage || "Copied";
      const originalText = button.textContent;

      if (textSelector) {
        copyText(
          textSelector,
          `[data-module="copy-button"][data-text-selector="${textSelector}"]`,
          successMessage,
          originalText,
        );
      }
    });
  },
};

export default CopyButton;
