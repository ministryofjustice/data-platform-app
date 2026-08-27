import accessibleAutocomplete from "accessible-autocomplete";

const MIN_QUERY_LENGTH = 3;
const DEBOUNCE_MS = 250;

function escapeHtml(value) {
  const element = document.createElement("div");
  element.textContent = value == null ? "" : String(value);
  return element.innerHTML;
}

function userToLabel(user) {
  if (!user) {
    return "";
  }
  if (typeof user === "string") {
    return user;
  }
  if (!user.email) {
    return user.display_name;
  }
  return user.display_name
    ? `${user.email} (${user.display_name})`
    : user.email;
}

function userToSuggestion(user) {
  if (!user) {
    return "";
  }
  if (typeof user === "string") {
    return escapeHtml(user);
  }
  const email = escapeHtml(user.email);
  if (!user.email) {
    return escapeHtml(user.display_name);
  }
  if (!user.display_name) {
    return email;
  }
  return `${email} <span class="autocomplete__option-hint">${escapeHtml(user.display_name)}</span>`;
}

function findFieldsContainer(mount) {
  return mount.closest(".govuk-form-group") || mount.parentElement;
}

function findHiddenField(mount) {
  const container = findFieldsContainer(mount);
  return container
    ? container.querySelector('input[type="hidden"][data-entra-user-id]')
    : null;
}

function findSnapshotFields(mount) {
  const container = findFieldsContainer(mount);
  return {
    email: container
      ? container.querySelector('input[type="hidden"][data-entra-user-email]')
      : null,
    name: container
      ? container.querySelector('input[type="hidden"][data-entra-user-name]')
      : null,
  };
}

function fetchUsers(searchUrl, query, signal) {
  return fetch(`${searchUrl}?q=${encodeURIComponent(query)}`, {
    signal,
    headers: { "X-Requested-With": "XMLHttpRequest" },
    credentials: "same-origin",
  }).then((response) => {
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    return response.json();
  });
}

function enhance(mount, searchUrl, hiddenField) {
  // Snapshot fields let the confirmation page redisplay the choice without
  // another Graph call; they travel in the submitted form data.
  const snapshot = findSnapshotFields(mount);

  // Remote search state shared by the source and no-results message.
  let status = "idle";
  let confirmedLabel = null;
  let debounceTimer;
  let controller;

  const clearSelection = () => {
    hiddenField.value = "";
    if (snapshot.email) {
      snapshot.email.value = "";
    }
    if (snapshot.name) {
      snapshot.name.value = "";
    }
    confirmedLabel = null;
  };

  const runSearch = (query, populateResults) => {
    // Cancel any in-flight request so its response can't overwrite this one.
    if (controller) {
      controller.abort();
    }
    controller = new AbortController();
    status = "loading";

    fetchUsers(searchUrl, query, controller.signal)
      .then((data) => {
        status = "results";
        populateResults(data.results || []);
      })
      .catch((error) => {
        if (error.name === "AbortError") {
          return;
        }
        status = "error";
        populateResults([]);
      });
  };

  const source = (query, populateResults) => {
    const trimmed = query.trim();
    if (trimmed.length < MIN_QUERY_LENGTH) {
      status = "idle";
      populateResults([]);
      return;
    }

    // Wait for a pause in typing before hitting the server.
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(
      () => runSearch(trimmed, populateResults),
      DEBOUNCE_MS,
    );
  };

  const noResultsText = () => {
    if (status === "loading") {
      return "Searching…";
    }
    if (status === "error") {
      return "Sorry, there was a problem searching for users";
    }
    return "No users found";
  };

  accessibleAutocomplete({
    element: mount,
    id: mount.dataset.inputId,
    // Empty name keeps the visible input out of the submitted form data.
    name: "",
    minLength: MIN_QUERY_LENGTH,
    confirmOnBlur: false,
    source,
    templates: { inputValue: userToLabel, suggestion: userToSuggestion },
    onConfirm: (user) => {
      if (user && user.id) {
        hiddenField.value = user.id;
        if (snapshot.email) {
          snapshot.email.value = user.email || "";
        }
        if (snapshot.name) {
          snapshot.name.value = user.display_name || "";
        }
        confirmedLabel = userToLabel(user);
      }
    },
    tNoResults: noResultsText,
  });

  const input = mount.querySelector(".autocomplete__input");
  if (input) {
    // A confirmed selection is only valid while the text matches it.
    input.addEventListener("input", () => {
      if (input.value !== confirmedLabel) {
        clearSelection();
      }
    });
  }
}

const EntraUserAutocomplete = {
  init: function (scope = document) {
    const mounts = scope.querySelectorAll(
      '[data-module="entra-user-autocomplete"]',
    );

    mounts.forEach((mount) => {
      if (mount.dataset.initialised === "true") {
        return;
      }

      const searchUrl = mount.dataset.searchUrl;
      const hiddenField = findHiddenField(mount);
      if (!searchUrl || !mount.dataset.inputId || !hiddenField) {
        return;
      }

      mount.dataset.initialised = "true";
      enhance(mount, searchUrl, hiddenField);
    });
  },
};

export default EntraUserAutocomplete;
