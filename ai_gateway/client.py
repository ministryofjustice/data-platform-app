"""Client for the LiteLLM AI Gateway management API."""

from __future__ import annotations

from typing import Any

import httpx
from django.conf import settings

from ai_gateway.exceptions import AIGatewayAPIError


class AIGatewayClient:
    """Talks to the LiteLLM AI Gateway management API."""

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
    ) -> dict[str, Any]:
        """Send a request and return the parsed JSON body, raising on error responses."""
        response = self._client.request(method, path, json=json)
        if response.is_error:
            raise AIGatewayAPIError(response.status_code, response.text)
        return response.json()

    def list_models(self) -> list[str]:
        """Return the ids of the models available on the gateway."""
        data = self._request("GET", "/v1/models")
        return [model["id"] for model in data.get("data", [])]

    def create_team(self, name: str) -> str:
        """Create a team named ``name`` and return its generated team id."""
        data = self._request("POST", "/team/new", json={"team_alias": name})
        return data["team_id"]

    def delete_team(self, team_id: str) -> None:
        """Delete the team identified by ``team_id``."""
        self._request("POST", "/team/delete", json={"team_ids": [team_id]})

    def generate_key(self, team_id: str, key_alias: str | None = None) -> dict[str, Any]:
        """Generate a virtual key for ``team_id`` and return the gateway response.

        ``key_alias`` tags the key so it can be managed later (for example deleted
        by alias) without the plaintext.
        """
        payload: dict[str, Any] = {"team_id": team_id}
        if key_alias is not None:
            payload["key_alias"] = key_alias
        return self._request("POST", "/key/generate", json=payload)

    def regenerate_key(self, key: str) -> str:
        """Rotate ``key`` and return the new key string."""
        data = self._request("POST", f"/key/{key}/regenerate")
        return data["key"]

    def delete_key(self, key: str) -> None:
        """Delete the virtual key ``key``."""
        self._request("POST", "/key/delete", json={"keys": [key]})
