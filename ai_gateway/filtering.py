from __future__ import annotations

from typing import Any

VISIBLE_LIMIT = 10


def filter_models(
    models: list[dict[str, Any]],
    search: str = "",
    provider: str = "",
    family: str = "",
) -> list[dict[str, Any]]:
    """Return the models matching every supplied filter, preserving input order.

    An empty filter value means "no constraint" for that dimension. ``search`` is
    matched case-insensitively against the model's display name.
    """
    normalised_search = search.strip().lower()

    matches: list[dict[str, Any]] = []
    for model in models:
        if provider and model.get("provider") != provider:
            continue
        if family and model.get("family") != family:
            continue
        if normalised_search and normalised_search not in model.get("display_name", "").lower():
            continue

        matches.append(model)

    return matches
