"""Client for the Microsoft Graph directory API.

Talks to Microsoft Graph on behalf of the signed-in user, using their cached
delegated access token.
"""

from __future__ import annotations

from typing import Any

import httpx
from azure_auth.handlers import AuthHandler


class EntraDirectoryError(Exception):
    """Base error for Microsoft Graph directory requests."""


class EntraAuthenticationError(EntraDirectoryError):
    """Raised when no delegated access token is available for the request."""


class EntraRequestError(EntraDirectoryError):
    """Raised when a Microsoft Graph request fails."""


class MicrosoftGraphClient:
    """Query the Microsoft Graph directory on behalf of the signed-in user."""

    BASE_URL = "https://graph.microsoft.com/v1.0/"
    SEARCH_SELECT = "id,displayName,mail"
    USER_SELECT = "id,displayName,mail,givenName,surname"
    DEFAULT_TIMEOUT = 5.0
    DEFAULT_RESULT_LIMIT = 10

    def __init__(
        self,
        access_token: str,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        client: httpx.Client | None = None,
    ) -> None:
        """Build a client, optionally with an injected ``httpx.Client`` for testing."""
        self._client = client or httpx.Client(
            base_url=self.BASE_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=timeout,
        )

    @classmethod
    def from_request(cls, request, **kwargs) -> MicrosoftGraphClient:
        """Build a client from the signed-in user's cached delegated token."""
        token = AuthHandler(request).get_token_from_cache()
        access_token = token.get("access_token") if token else None
        if not access_token:
            raise EntraAuthenticationError("No delegated access token is available")
        return cls(access_token, **kwargs)

    def __enter__(self) -> MicrosoftGraphClient:
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def close(self) -> None:
        """Close underlying HTTP resources."""
        self._client.close()

    def search_users_by_email(
        self, query: str, *, limit: int = DEFAULT_RESULT_LIMIT
    ) -> list[dict[str, Any]]:
        """Return directory users whose email starts with ``query``."""
        # Double single quotes to escape the OData string literal.
        escaped_query = query.replace("'", "''")
        try:
            response = self._client.get(
                "users",
                params={
                    "$filter": f"startsWith(mail,'{escaped_query}')",
                    "$select": self.SEARCH_SELECT,
                    "$top": str(limit),
                    "$count": "true",
                },
                # ConsistencyLevel lets Graph evaluate the startsWith filter.
                headers={"ConsistencyLevel": "eventual"},
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise EntraRequestError(str(error)) from error
        return response.json().get("value", [])

    def get_user(self, oid: str) -> dict[str, Any]:
        """Return a single directory user by object id."""
        try:
            response = self._client.get(
                f"users/{oid}",
                params={"$select": self.USER_SELECT},
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise EntraRequestError(str(error)) from error
        return response.json()
