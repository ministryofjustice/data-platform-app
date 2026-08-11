"""Service layer for AI Gateway key operations."""

from __future__ import annotations

import secrets
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.utils.text import slugify

from ai_gateway.client import AIGatewayClient
from ai_gateway.models import Key, Team
from projects.models import Project
from users.models import User


class KeyService:
    """Coordinates AI Gateway key operations for a project.

    Holds an ``AIGatewayClient`` so related operations share one client and a
    single lifecycle. Use as a context manager to close the client on exit::

        with KeyService.from_settings() as service:
            service.create_key(project, name, models, created_by)
    """

    GENERALLY_AVAILABLE_KEY = "ai_model_generally_available"

    def __init__(self, client: AIGatewayClient) -> None:
        self._client = client

    @classmethod
    def from_settings(cls) -> KeyService:
        """Build a service backed by a client configured from Django settings."""
        return cls(AIGatewayClient.from_settings())

    def __enter__(self) -> KeyService:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying gateway client."""
        self._client.close()

    def list_available_models(self, project: Project) -> list[dict[str, Any]]:
        """Return the models ``project`` may select when creating a key.

        Includes models marked as generally available plus any models granted to
        the project's gateway team through its access groups. When the team does
        not exist yet (the first key), only generally available models are shown.
        """
        access_group_models = self._team_access_group_models(project)
        models = []
        for model in self._client.list_models_v1_info():
            litellm_params = model.get("litellm_params", {})
            generally_available = litellm_params.get(self.GENERALLY_AVAILABLE_KEY) is True

            if not generally_available and model.get("model_name") not in access_group_models:
                continue

            models.append(self._enrich_model(model))

        return models

    def _team_access_group_models(self, project: Project) -> set[str]:
        """Return model names granted to ``project``'s team via its access groups."""
        try:
            team = project.ai_gateway_team
        except Team.DoesNotExist:
            return set()

        data = self._client.team_info(team.litellm_team_id)
        return set(data.get("team_info", {}).get("access_group_models", []))

    def _enrich_model(self, model: dict[str, Any]) -> dict[str, Any]:
        """Return a copy of ``model`` with display and pricing fields added."""
        model = model.copy()
        litellm_params = model.get("litellm_params", {})
        model_info = model.get("model_info", {})

        input_cost = model_info.get("input_cost_per_token")
        output_cost = model_info.get("output_cost_per_token")

        model["input_cost_per_million"] = (
            input_cost * 1_000_000 if input_cost is not None else None
        )
        model["output_cost_per_million"] = (
            output_cost * 1_000_000 if output_cost is not None else None
        )
        model["display_name"] = litellm_params.get("ai_model_name") or model.get("model_name")
        model["provider"] = litellm_params.get("ai_model_provider")
        model["family"] = litellm_params.get("ai_model_family")

        return model

    def create_key(self, project: Project, name: str, models: list[str], created_by: User) -> str:
        """Generate a gateway key for ``project`` and persist its metadata.

        Lazily creates the project's gateway team, calls the gateway to generate
        a key, then stores metadata and an encrypted copy of the secret. ``name``
        is the user-facing name (unique per project); a globally unique ``litellm_alias`` is
        derived from it for the gateway. Returns the plaintext key, which is shown to the user
        once.
        """
        team = self._get_or_create_team(project)
        litellm_alias = self._build_alias(project, name)
        data = self._client.generate_key(
            team.litellm_team_id, key_alias=litellm_alias, models=models
        )

        plaintext_key = data["key"]
        Key.objects.create(
            project=project,
            name=name,
            litellm_alias=litellm_alias,
            litellm_secret=plaintext_key,
            litellm_token=data.get("token", ""),
            masked_key=self._mask_key(plaintext_key),
            created_by=created_by,
        )
        return plaintext_key

    def regenerate_key(self, key: Key) -> str:
        """Regenerate a gateway key for ``key`` and persist its metadata."""

        # Avoid holding a DB row lock while making a network call to the gateway.
        old_secret = Key.objects.values_list("litellm_secret", flat=True).get(pk=key.pk)
        plaintext_key = self._client.regenerate_key(old_secret)

        with transaction.atomic():
            db_key = Key.objects.select_for_update().get(pk=key.pk)
            db_key.litellm_secret = plaintext_key
            db_key.masked_key = self._mask_key(plaintext_key)
            db_key.save(update_fields=["litellm_secret", "masked_key", "modified"])

        return plaintext_key

    def bulk_delete_keys(self, keys: list[str]) -> None:
        """Bulk delete gateway keys identified by their secrets."""
        if keys:
            self._client.bulk_delete_keys(keys)

    def delete_team(self, team_id: str) -> None:
        """Delete the gateway team identified by ``team_id``."""
        self._client.delete_team(team_id)

    def get_models_for_key(self, key: Key) -> list[str]:
        """Return model names for ``key``, using a short-lived cache.

        Cached entries are keyed by ``key.pk`` and ``key.modified`` so local
        key updates immediately shift lookups to a new cache key. A timeout is
        still applied to refresh data that may change remotely on the gateway.
        """
        cache_key = self._key_models_cache_key(key)
        cached_models = cache.get(cache_key)
        if cached_models is not None:
            return cached_models

        data = self._client.key_info(key.litellm_secret)
        models = data.get("info", {}).get("models", [])
        cache.set(cache_key, models, timeout=self._key_models_cache_timeout())
        return models

    def delete_key(self, key: Key) -> None:
        """Delete the virtual key from the gateway and remove its metadata."""
        self._client.delete_key(key.litellm_secret)
        key.delete()

    @staticmethod
    def _key_models_cache_key(key: Key) -> str:
        """Return a versioned cache key for model names associated with ``key``."""
        return f"ai_gateway:key-models:{key.pk}:{key.modified.isoformat()}"

    @staticmethod
    def _key_models_cache_timeout() -> int:
        """Return model-cache timeout in seconds from settings or default."""
        return int(getattr(settings, "AI_GATEWAY_KEY_MODELS_CACHE_TIMEOUT", 300))

    def _get_or_create_team(self, project: Project) -> Team:
        """Return the project's gateway team, creating it on the gateway if needed."""
        try:
            return project.ai_gateway_team
        except Team.DoesNotExist:
            access_group_id = self._client.get_access_group_id(self._default_access_group_name())
            team_id = self._client.create_team(str(project.uuid), [access_group_id])
            return Team.objects.create(project=project, litellm_team_id=team_id)

    @staticmethod
    def _default_access_group_name() -> str:
        """Return configured default access group name or raise if missing."""
        name = settings.DEFAULT_ACCESS_GROUP_NAME
        if not name:
            raise ImproperlyConfigured("DEFAULT_ACCESS_GROUP_NAME is not configured")
        return name

    @staticmethod
    def _build_alias(project: Project, name: str) -> str:
        """Build a globally unique, readable gateway alias from a project and name."""
        return f"{project.uuid}-{slugify(name)}-{secrets.token_hex(6)}"

    @staticmethod
    def _mask_key(key: str) -> str:
        """Return a display-safe fingerprint of a key, never the full secret."""
        if len(key) <= 4:
            return "..."
        return f"...{key[-4:]}"


class AccessGroupService:
    """Manages the access groups assigned to a project's gateway team.

    Holds an ``AIGatewayClient`` so related operations share one client and a
    single lifecycle. Use as a context manager to close the client on exit::

        with AccessGroupService.from_settings() as service:
            service.set_team_access_groups(team, access_group_ids)
    """

    def __init__(self, client: AIGatewayClient) -> None:
        self._client = client

    @classmethod
    def from_settings(cls) -> AccessGroupService:
        """Build a service backed by a client configured from Django settings."""
        return cls(AIGatewayClient.from_settings())

    def __enter__(self) -> AccessGroupService:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying gateway client."""
        self._client.close()

    def list_access_groups(self) -> list[dict[str, Any]]:
        """Return all access groups configured on the gateway."""
        return self._client.list_access_groups()

    def get_team_access_group_ids(self, team: Team) -> list[str]:
        """Return the ids of the access groups currently assigned to ``team``."""
        return self._client.get_team_access_group_ids(team.litellm_team_id)

    def set_team_access_groups(self, team: Team, access_group_ids: list[str]) -> None:
        """Replace the access groups assigned to ``team``."""
        self._client.update_team_access_groups(team.litellm_team_id, access_group_ids)
