from __future__ import annotations

from typing import Any

VISIBLE_LIMIT = 10


def model_display_name(model: dict[str, Any]) -> str:
    """Return the human-facing name used to display and search a model."""
    litellm_params = model.get("litellm_params", {})
    return litellm_params.get("ai_model_name") or model.get("model_name", "")


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
        litellm_params = model.get("litellm_params", {})

        if provider and litellm_params.get("ai_model_provider") != provider:
            continue
        if family and litellm_params.get("ai_model_family") != family:
            continue
        if normalised_search and normalised_search not in model_display_name(model).lower():
            continue

        matches.append(model)

    return matches
