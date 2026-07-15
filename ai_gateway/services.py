"""Service layer for AI Gateway key operations."""

from __future__ import annotations

import secrets

from django.conf import settings
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

    def regenerate_key(self, project: Project, name: str, key: str) -> str:
        """
        Regenerate a gateway key for ``project`` and persist its metadata.
        """

        plaintext_key = self._client.regenerate_key(key)

        with transaction.atomic():
            db_key = Key.objects.select_for_update().get(project=project, name=name)
            db_key.litellm_secret = plaintext_key
            db_key.masked_key = self._mask_key(plaintext_key)
            db_key.save(update_fields=["litellm_secret", "masked_key", "modified"])

        return plaintext_key

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
