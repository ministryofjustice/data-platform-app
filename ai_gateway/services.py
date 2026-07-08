"""Service layer for AI Gateway key operations."""

from __future__ import annotations

import secrets

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
            service.create_key(project, name, user)
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

    def list_models(self) -> list[str]:
        """Return the ids of the models available on the gateway."""
        return self._client.list_models()

    def create_key(self, project: Project, name: str, models: list[str], created_by: User) -> str:
        """Generate a gateway key for ``project`` and persist its metadata.

        Lazily creates the project's gateway team, calls the gateway to generate
        a key, then stores metadata only. ``name`` is the user-facing name
        (unique per project); a globally unique ``litellm_alias`` is derived from
        it for the gateway. Returns the plaintext key, which is shown to the user
        once and never stored.
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

    def _get_or_create_team(self, project: Project) -> Team:
        """Return the project's gateway team, creating it on the gateway if needed."""
        try:
            return project.ai_gateway_team
        except Team.DoesNotExist:
            team_id = self._client.create_team(project.name)
            return Team.objects.create(project=project, litellm_team_id=team_id)

    @staticmethod
    def _build_alias(project: Project, name: str) -> str:
        """Build a globally unique, readable gateway alias from a project and name."""
        return f"{project.slug}-{slugify(name)}-{secrets.token_hex(6)}"

    @staticmethod
    def _mask_key(key: str) -> str:
        """Return a display-safe fingerprint of a key, never the full secret."""
        if len(key) <= 10:
            return "..."
        return f"{key[:6]}...{key[-4:]}"
