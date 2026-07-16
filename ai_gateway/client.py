"""Client for the LiteLLM AI Gateway management API."""

from __future__ import annotations

from typing import Any, cast

import httpx
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from ai_gateway.exceptions import AIGatewayAPIError, AIGatewayTransportError


class AIGatewayClient:
    """Talks to the LiteLLM AI Gateway management API."""

    DEFAULT_TEAM_BUDGET = 1000
    DEFAULT_TEAM_BUDGET_DURATION = "monthly"
    DEFAULT_TEAM_TPM_LIMIT = 500_000
    DEFAULT_TEAM_RPM_LIMIT = 100

    def __init__(
        self,
        base_url: str,
        master_key: str,
        timeout: float = 10.0,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        """Build a client, optionally with an injected ``httpx.Client`` for testing."""
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {master_key}"},
            timeout=timeout,
        )

    @classmethod
    def from_settings(cls) -> AIGatewayClient:
        """Build a client from ``AI_GATEWAY_URL`` and ``AI_GATEWAY_MASTER_KEY`` settings."""
        if not settings.AI_GATEWAY_URL or not settings.AI_GATEWAY_MASTER_KEY:
            raise ImproperlyConfigured(
                "AI_GATEWAY_URL and AI_GATEWAY_MASTER_KEY must be configured"
            )
        return cls(
            base_url=settings.AI_GATEWAY_URL,
            master_key=settings.AI_GATEWAY_MASTER_KEY,
        )

    def close(self) -> None:
        """Close underlying HTTP resources."""
        self._client.close()

    def _request(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Send a request and return the parsed JSON body, raising on error responses."""
        try:
            response = self._client.request(method, path, json=json, params=params)
        except httpx.HTTPError as error:
            raise AIGatewayTransportError(str(error)) from error
        if response.is_error:
            raise AIGatewayAPIError(response.status_code, response.text)
        return response.json()

    def list_models(self) -> list[str]:
        """Return the ids of the models available on the gateway."""
        data = self._request("GET", "/v1/models")
        return [model["id"] for model in data.get("data", [])]

    def _get_access_group(self, name: str) -> dict[str, Any]:
        """Return the access group whose name matches ``name``.

        Resolves the group by its stable name rather than an environment-specific
        id, and raises if no group or more than one group matches.
        """
        groups = cast("list[dict[str, Any]]", self._request("GET", "/v1/access_group"))
        matches = [group for group in groups if group.get("access_group_name") == name]
        if not matches:
            raise AIGatewayAPIError(404, f"No access group named {name!r}")
        if len(matches) > 1:
            raise AIGatewayAPIError(409, f"Multiple access groups named {name!r}")
        return matches[0]

    def get_access_group_id(self, name: str) -> str:
        """Return the id of the access group named ``name``."""
        return self._get_access_group(name)["access_group_id"]

    def list_models_for_access_group(self, name: str) -> list[str]:
        """Return the model names available in the access group named ``name``."""
        return self._get_access_group(name)["access_model_names"]

    def create_team(self, team_alias: str, access_group_ids: list[str] | None = None) -> str:
        """Create a team with alias ``team_alias`` and return its generated team id."""
        post_data = {
            "team_alias": team_alias,
            "max_budget": self.DEFAULT_TEAM_BUDGET,
            "budget_duration": self.DEFAULT_TEAM_BUDGET_DURATION,
            "tpm_limit": self.DEFAULT_TEAM_TPM_LIMIT,
            "rpm_limit": self.DEFAULT_TEAM_RPM_LIMIT,
        }
        if access_group_ids is not None:
            post_data["access_group_ids"] = access_group_ids

        data = self._request(
            "POST",
            "/team/new",
            json=post_data,
        )
        return data["team_id"]

    def delete_team(self, team_id: str) -> None:
        """Delete the team identified by ``team_id``."""
        self._request("POST", "/team/delete", json={"team_ids": [team_id]})

    def generate_key(
        self,
        team_id: str,
        key_alias: str | None = None,
        models: list[str] | None = None,
    ) -> dict[str, Any]:
        """Generate a virtual key for ``team_id`` and return the gateway response.

        ``key_alias`` tags the key so it can be managed later (for example deleted
        by alias) without the plaintext. ``models`` scopes the key to the given
        model ids; when omitted the gateway applies its default access.
        """
        payload: dict[str, Any] = {"team_id": team_id}
        if key_alias is not None:
            payload["key_alias"] = key_alias
        if models is not None:
            payload["models"] = models
        return self._request("POST", "/key/generate", json=payload)

    def regenerate_key(self, key: str) -> str:
        """Rotate ``key`` and return the new key string."""
        data = self._request("POST", f"/key/{key}/regenerate")
        return data["key"]

    def delete_key(self, key: str) -> None:
        """Delete the virtual key ``key``."""
        self._request("POST", "/key/delete", json={"keys": [key]})

    def key_info(self, key: str) -> dict[str, Any]:
        """Return metadata about the virtual key ``key``."""
        return self._request("GET", "/key/info", params={"key": key})
