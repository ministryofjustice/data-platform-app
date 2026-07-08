import json

import httpx
import pytest

from ai_gateway import AIGatewayAPIError, AIGatewayClient


def build_client(handler):
    """Build an AIGatewayClient whose HTTP calls are served by ``handler``."""
    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(
        base_url="http://ai-gateway.test",
        headers={"Authorization": "Bearer sk-test-master-key"},
        transport=transport,
    )
    return AIGatewayClient(
        base_url="http://ai-gateway.test",
        master_key="sk-test-master-key",
        client=http_client,
    )


class TestListModels:
    def test_returns_model_ids(self):
        def handler(request):
            assert request.method == "GET"
            assert request.url.path == "/v1/models"
            return httpx.Response(200, json={"data": [{"id": "gpt-4"}, {"id": "claude-3"}]})

        client = build_client(handler)

        assert client.list_models() == ["gpt-4", "claude-3"]

    def test_empty_when_no_models(self):
        client = build_client(lambda request: httpx.Response(200, json={"data": []}))

        assert client.list_models() == []


class TestCreateTeam:
    def test_sends_project_name_and_returns_team_id(self):
        def handler(request):
            assert request.method == "POST"
            assert request.url.path == "/team/new"
            assert json.loads(request.read()) == {"team_alias": "my-project"}
            return httpx.Response(200, json={"team_id": "team-123"})

        client = build_client(handler)

        assert client.create_team("my-project") == "team-123"


class TestDeleteTeam:
    def test_posts_team_id(self):
        captured = {}

        def handler(request):
            assert request.method == "POST"
            assert request.url.path == "/team/delete"
            captured["body"] = json.loads(request.read())
            return httpx.Response(200, json={})

        client = build_client(handler)
        client.delete_team("team-123")

        assert captured["body"] == {"team_ids": ["team-123"]}


class TestGenerateKey:
    def test_returns_generated_key(self):
        def handler(request):
            assert request.method == "POST"
            assert request.url.path == "/key/generate"
            assert json.loads(request.read()) == {"team_id": "team-123"}
            return httpx.Response(200, json={"key": "sk-generated", "token": "hash-1"})

        client = build_client(handler)

        assert client.generate_key("team-123") == {
            "key": "sk-generated",
            "token": "hash-1",
        }

    def test_sends_key_alias_when_given(self):
        def handler(request):
            assert json.loads(request.read()) == {
                "team_id": "team-123",
                "key_alias": "proj-abcd1234",
            }
            return httpx.Response(200, json={"key": "sk-generated", "token": "hash-1"})

        client = build_client(handler)

        result = client.generate_key("team-123", key_alias="proj-abcd1234")

        assert result["key"] == "sk-generated"

    def test_sends_models_when_given(self):
        def handler(request):
            assert json.loads(request.read()) == {
                "team_id": "team-123",
                "key_alias": "proj-abcd1234",
                "models": ["gpt-4", "claude-3"],
            }
            return httpx.Response(200, json={"key": "sk-generated", "token": "hash-1"})

        client = build_client(handler)

        result = client.generate_key(
            "team-123", key_alias="proj-abcd1234", models=["gpt-4", "claude-3"]
        )

        assert result["key"] == "sk-generated"


class TestRegenerateKey:
    def test_returns_new_key(self):
        def handler(request):
            assert request.method == "POST"
            assert request.url.path == "/key/sk-old/regenerate"
            return httpx.Response(200, json={"key": "sk-new"})

        client = build_client(handler)

        assert client.regenerate_key("sk-old") == "sk-new"


class TestDeleteKey:
    def test_posts_key(self):
        captured = {}

        def handler(request):
            assert request.method == "POST"
            assert request.url.path == "/key/delete"
            captured["body"] = json.loads(request.read())
            return httpx.Response(200, json={})

        client = build_client(handler)
        client.delete_key("sk-old")

        assert captured["body"] == {"keys": ["sk-old"]}


class TestErrorHandling:
    def test_non_success_raises_api_error(self):
        client = build_client(lambda request: httpx.Response(401, text="Unauthorized"))

        with pytest.raises(AIGatewayAPIError) as exc_info:
            client.list_models()

        assert exc_info.value.status_code == 401
        assert exc_info.value.message == "Unauthorized"


class TestAuthentication:
    def test_master_key_sent_as_bearer_token(self):
        captured = {}

        def handler(request):
            captured["auth"] = request.headers.get("Authorization")
            return httpx.Response(200, json={"data": []})

        client = build_client(handler)
        client.list_models()

        assert captured["auth"] == "Bearer sk-test-master-key"


class TestFromSettings:
    def test_reads_url_and_master_key_from_settings(self, settings):
        settings.AI_GATEWAY_URL = "http://gateway.example"
        settings.AI_GATEWAY_MASTER_KEY = "sk-from-settings"

        client = AIGatewayClient.from_settings()

        assert client._base_url == "http://gateway.example"
        assert client._client.headers["Authorization"] == "Bearer sk-from-settings"
