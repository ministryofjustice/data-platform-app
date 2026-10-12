from __future__ import annotations

from fnmatch import fnmatchcase
from typing import Any

VISIBLE_LIMIT = 10


def exclude_catalogue_models(
    models: list[dict[str, Any]], rules: list[dict[str, str]]
) -> list[dict[str, Any]]:
    """Exclude models matching any rule's dotted field path and case-sensitive glob.

    Missing fields and non-string values do not match. Input ordering is preserved.
    """
    included = []
    for model in models:
        for rule in rules:
            value: Any = model
            for field in rule["field"].split("."):
                value = value.get(field) if isinstance(value, dict) else None
            if isinstance(value, str) and fnmatchcase(value, rule["pattern"]):
                break
        else:
            included.append(model)
    return included


def filter_models(
    models: list[dict[str, Any]],
    search: str = "",
    provider: str = "",
    family: str = "",
    region: str = "",
    selected_model_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Return the models matching every supplied filter, with selected models moved first.

    An empty filter value means "no constraint" for that dimension. ``search`` is
    matched case-insensitively against the model's display name. Region uses exact
    matching. Without ``selected_model_ids``, input order is otherwise preserved.
    """
    normalised_search = search.strip().lower()

    matches: list[dict[str, Any]] = []
    for model in models:
        if provider and model.get("provider") != provider:
            continue
        if family and model.get("family") != family:
            continue
        if region and model.get("region") != region:
            continue
        if normalised_search and normalised_search not in model.get("display_name", "").lower():
            continue

        matches.append(model)

    if selected_model_ids:
        matches.sort(key=lambda model: model["model_name"] not in selected_model_ids)

    return matches
