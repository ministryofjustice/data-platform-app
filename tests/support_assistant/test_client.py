import json

import httpx
import pytest
from django.core.exceptions import ImproperlyConfigured

from ai_gateway.exceptions import AIGatewayAPIError, AIGatewayTransportError
from support_assistant.client import ChatCompletionsClient


def build_client(handler):
    http_client = httpx.Client(
        base_url="http://ai-gateway.test", transport=httpx.MockTransport(handler)
    )
    return ChatCompletionsClient(
        base_url="http://ai-gateway.test",
        api_key="sk-test",
        model="test-model",
        client=http_client,
    )


def completion(content):
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


class TestChatCompletionsClient:
    def test_posts_messages_and_returns_content(self):
        messages = [{"role": "user", "content": "Hi"}]

        def handler(request):
            assert request.method == "POST"
            assert request.url.path == "/v1/chat/completions"
            assert json.loads(request.read()) == {
                "model": "test-model",
                "messages": messages,
                "temperature": 0,
            }
            return httpx.Response(200, json=completion("Hello"))

        assert build_client(handler).complete(messages) == "Hello"

    def test_raises_api_error_on_error_response(self):
        client = build_client(lambda request: httpx.Response(429, text="Budget exceeded"))

        with pytest.raises(AIGatewayAPIError) as error:
            client.complete([])

        assert error.value.status_code == 429

    def test_raises_transport_error(self):
        def handler(request):
            raise httpx.ReadTimeout("timed out")

        with pytest.raises(AIGatewayTransportError):
            build_client(handler).complete([])

    @pytest.mark.parametrize(
        "body", [{"choices": []}, {"unexpected": True}, completion(None), ["not", "a", "dict"]]
    )
    def test_raises_api_error_on_unexpected_body(self, body):
        client = build_client(lambda request: httpx.Response(200, json=body))

        with pytest.raises(AIGatewayAPIError):
            client.complete([])

    def test_raises_api_error_on_invalid_json(self):
        client = build_client(lambda request: httpx.Response(200, text="<html>"))

        with pytest.raises(AIGatewayAPIError):
            client.complete([])

    def test_from_settings_uses_dedicated_key(self):
        with ChatCompletionsClient.from_settings() as client:
            assert client.model == "test-model"
            assert (
                client._client.headers["Authorization"] == "Bearer sk-test-support-assistant-key"
            )
            assert str(client._client.base_url) == "http://ai-gateway.test"

    @pytest.mark.parametrize(
        "setting",
        [
            "SUPPORT_ASSISTANT_GATEWAY_URL",
            "SUPPORT_ASSISTANT_API_KEY",
            "SUPPORT_ASSISTANT_MODEL",
        ],
    )
    def test_from_settings_requires_configuration(self, settings, setting):
        setattr(settings, setting, None)

        with pytest.raises(ImproperlyConfigured):
            ChatCompletionsClient.from_settings()
