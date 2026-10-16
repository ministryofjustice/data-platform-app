"""Client for the AI Gateway's OpenAI-compatible chat completions API."""

from __future__ import annotations

from typing import Any

import httpx
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from ai_gateway.exceptions import AIGatewayAPIError, AIGatewayTransportError


class ChatCompletionsClient:
    """Calls ``/v1/chat/completions`` using a dedicated virtual key, never the master key."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 30.0,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self.model = model
        self._client = client or httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )

    @classmethod
    def from_settings(cls) -> ChatCompletionsClient:
        if not (
            settings.SUPPORT_ASSISTANT_GATEWAY_URL
            and settings.SUPPORT_ASSISTANT_API_KEY
            and settings.SUPPORT_ASSISTANT_MODEL
        ):
            raise ImproperlyConfigured(
                "SUPPORT_ASSISTANT_GATEWAY_URL, SUPPORT_ASSISTANT_API_KEY and "
                "SUPPORT_ASSISTANT_MODEL must be configured"
            )
        return cls(
            base_url=settings.SUPPORT_ASSISTANT_GATEWAY_URL,
            api_key=settings.SUPPORT_ASSISTANT_API_KEY,
            model=settings.SUPPORT_ASSISTANT_MODEL,
            timeout=settings.SUPPORT_ASSISTANT_TIMEOUT,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> ChatCompletionsClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def complete(self, messages: list[dict[str, str]]) -> str:
        """Send chat messages and return the assistant's reply text."""
        payload: dict[str, Any] = {"model": self.model, "messages": messages, "temperature": 0}
        try:
            response = self._client.post("/v1/chat/completions", json=payload)
        except httpx.HTTPError as error:
            raise AIGatewayTransportError(str(error)) from error
        if response.is_error:
            raise AIGatewayAPIError(response.status_code, response.text)
        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as error:
            raise AIGatewayAPIError(response.status_code, "Unexpected response shape") from error
        if not isinstance(content, str):
            raise AIGatewayAPIError(response.status_code, "Response contained no text")
        return content
