"""Service layer for AI Gateway key operations."""

from __future__ import annotations

import secrets
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
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

    def list_default_models(self) -> list[str]:
        """Return the model names in the default (generally available) access group."""
        return self._client.list_models_for_access_group(self._default_access_group_name())

    def list_selectable_models_for_key(self) -> list[dict[str, Any]]:
        """Return model records that can be selected when creating a key."""
        return self._client.list_selectable_models_for_key()

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
