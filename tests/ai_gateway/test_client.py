import json

import httpx
import pytest
from django.core.exceptions import ImproperlyConfigured

from ai_gateway.client import AIGatewayClient
from ai_gateway.exceptions import AIGatewayAPIError, AIGatewayTransportError


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


class TestCreateTeam:
    def test_sends_team_alias_and_returns_team_id(self):
        def handler(request):
            if request.url.path == "/organization/list":
                return organization_list_handler(request)

            assert request.method == "POST"
            assert request.url.path == "/team/new"
            assert json.loads(request.read()) == {
                "team_alias": "project-uuid",
                "max_budget": 500,
                "budget_duration": "monthly",
                "tpm_limit": 500000,
                "rpm_limit": 100,
                "models": ["no-default-models"],
                "organization_id": "org-123",
            }
            return httpx.Response(200, json={"team_id": "team-123"})

        client = build_client(handler)

        assert client.create_team("project-uuid") == "team-123"

    def test_includes_access_group_ids_when_given(self):
        def handler(request):
            if request.url.path == "/organization/list":
                return organization_list_handler(request)

            assert request.method == "POST"
            assert request.url.path == "/team/new"
            assert json.loads(request.read()) == {
                "team_alias": "project-uuid",
                "max_budget": 500,
                "budget_duration": "monthly",
                "tpm_limit": 500000,
                "rpm_limit": 100,
                "models": ["no-default-models"],
                "organization_id": "org-123",
                "access_group_ids": ["ag-123", "ag-456"],
            }
            return httpx.Response(200, json={"team_id": "team-123"})

        client = build_client(handler)

        assert client.create_team("project-uuid", ["ag-123", "ag-456"]) == "team-123"


def organization_list_handler(request):
    """Serve the /organization/list endpoint for the MOJ organisation."""
    assert request.method == "GET"
    assert request.url.path == "/organization/list"
    assert request.url.params.get("org_alias") == "Ministry of Justice"
    return httpx.Response(
        200,
        json=[
            {
                "organization_id": "org-123",
                "organization_alias": "Ministry of Justice",
            }
        ],
    )


def access_group_list_handler(request):
    """Serve the /v1/access_group list endpoint with two named groups."""
    assert request.method == "GET"
    assert request.url.path == "/v1/access_group"
    return httpx.Response(
        200,
        json=[
            {
                "access_group_name": "other-models",
                "access_group_id": "ag-other",
                "access_model_names": ["gpt-3.5"],
            },
            {
                "access_group_name": "generally-available-models",
                "access_group_id": "ag-default",
                "access_model_names": ["gpt-4", "claude-3"],
            },
        ],
    )


class TestListModelsForAccessGroup:
    def test_returns_model_names_for_matching_group(self):
        client = build_client(access_group_list_handler)

        assert client.list_models_for_access_group("generally-available-models") == [
            "gpt-4",
            "claude-3",
        ]


class TestGetAccessGroupId:
    def test_returns_id_for_matching_group(self):
        client = build_client(access_group_list_handler)

        assert client.get_access_group_id("generally-available-models") == "ag-default"

    def test_raises_when_group_not_found(self):
        client = build_client(access_group_list_handler)

        with pytest.raises(AIGatewayAPIError) as exc_info:
            client.get_access_group_id("missing-models")

        assert exc_info.value.status_code == 404

    def test_raises_when_multiple_groups_match(self):
        def handler(request):
            return httpx.Response(
                200,
                json=[
                    {"access_group_name": "dupe", "access_group_id": "ag-1"},
                    {"access_group_name": "dupe", "access_group_id": "ag-2"},
                ],
            )

        client = build_client(handler)

        with pytest.raises(AIGatewayAPIError) as exc_info:
            client.get_access_group_id("dupe")

        assert exc_info.value.status_code == 409


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
    def test_returns_new_key_and_token(self):
        def handler(request):
            assert request.method == "POST"
            assert request.url.path == "/key/old-token-id/regenerate"
            return httpx.Response(200, json={"key": "sk-new", "token_id": "new-token-id"})

        client = build_client(handler)

        assert client.regenerate_key("old-token-id") == {
            "key": "sk-new",
            "token_id": "new-token-id",
        }


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


class TestListTeamKeys:
    def test_returns_full_key_objects_for_team(self):
        def handler(request):
            assert request.method == "GET"
            assert request.url.path == "/key/list"
            assert request.url.params.get("team_id") == "team-123"
            assert request.url.params.get("return_full_object") == "true"
            assert request.url.params.get("size") == "100"
            assert request.url.params.get("page") == "1"
            return httpx.Response(
                200,
                json={
                    "keys": [
                        {"token": "hash-1", "key_alias": "alias-1", "models": ["gpt-4"]},
                    ],
                    "total_pages": 1,
                },
            )

        client = build_client(handler)

        assert client.list_team_keys("team-123") == [
            {"token": "hash-1", "key_alias": "alias-1", "models": ["gpt-4"]},
        ]

    def test_pages_through_all_results(self):
        pages = {
            "1": {
                "keys": [{"token": "hash-1", "key_alias": "alias-1", "models": ["gpt-4"]}],
                "total_pages": 2,
            },
            "2": {
                "keys": [{"token": "hash-2", "key_alias": "alias-2", "models": ["claude-3"]}],
                "total_pages": 2,
            },
        }

        def handler(request):
            assert request.url.path == "/key/list"
            page = request.url.params.get("page")
            return httpx.Response(200, json=pages[page])

        client = build_client(handler)

        keys = client.list_team_keys("team-123")

        assert [key["token"] for key in keys] == ["hash-1", "hash-2"]

    def test_empty_when_team_has_no_keys(self):
        client = build_client(
            lambda request: httpx.Response(200, json={"keys": [], "total_pages": 1})
        )

        assert client.list_team_keys("team-123") == []


class TestUpdateKeyModels:
    def test_posts_key_and_models(self):
        captured = {}

        def handler(request):
            assert request.method == "POST"
            assert request.url.path == "/key/update"
            captured["body"] = json.loads(request.read())
            return httpx.Response(200, json={})

        client = build_client(handler)
        client.update_key_models("hash-1", ["gpt-4"])

        assert captured["body"] == {"key": "hash-1", "models": ["gpt-4"]}


class TestTeamInfo:
    def test_returns_team_info_for_team_id(self):
        def handler(request):
            assert request.method == "GET"
            assert request.url.path == "/team/info"
            assert request.url.params.get("team_id") == "team-123"
            return httpx.Response(
                200,
                json={
                    "team_id": "team-123",
                    "team_info": {"access_group_models": ["restricted-model"]},
                },
            )

        client = build_client(handler)

        assert client.team_info("team-123") == {
            "team_id": "team-123",
            "team_info": {"access_group_models": ["restricted-model"]},
        }


class TestListAccessGroups:
    def test_returns_all_access_groups(self):
        client = build_client(access_group_list_handler)

        groups = client.list_access_groups()

        assert [group["access_group_name"] for group in groups] == [
            "other-models",
            "generally-available-models",
        ]


class TestGetTeamAccessGroupIds:
    def test_returns_access_group_ids_from_team_info(self):
        def handler(request):
            assert request.method == "GET"
            assert request.url.path == "/team/info"
            assert request.url.params.get("team_id") == "team-123"
            return httpx.Response(
                200,
                json={"team_info": {"access_group_ids": ["ag-1", "ag-2"]}},
            )

        client = build_client(handler)

        assert client.get_team_access_group_ids("team-123") == ["ag-1", "ag-2"]

    def test_returns_empty_when_team_has_no_access_groups(self):
        def handler(request):
            return httpx.Response(200, json={"team_info": {}})

        client = build_client(handler)

        assert client.get_team_access_group_ids("team-123") == []


class TestUpdateTeamAccessGroups:
    def test_posts_team_id_and_access_group_ids(self):
        captured = {}

        def handler(request):
            assert request.method == "POST"
            assert request.url.path == "/team/update"
            captured["body"] = json.loads(request.read())
            return httpx.Response(200, json={})

        client = build_client(handler)
        client.update_team_access_groups("team-123", ["ag-1", "ag-2"])

        assert captured["body"] == {
            "team_id": "team-123",
            "access_group_ids": ["ag-1", "ag-2"],
        }


class TestErrorHandling:
    def test_non_success_raises_api_error(self):
        client = build_client(lambda request: httpx.Response(401, text="Unauthorized"))

        with pytest.raises(AIGatewayAPIError) as exc_info:
            client.list_models_v1_info()

        assert exc_info.value.status_code == 401
        assert exc_info.value.message == "Unauthorized"

    def test_transport_error_raises_gateway_transport_error(self):
        def handler(request):
            raise httpx.ConnectError("gateway unavailable")

        client = build_client(handler)

        with pytest.raises(AIGatewayTransportError) as exc_info:
            client.list_models_v1_info()

        assert "gateway unavailable" in exc_info.value.message


class TestAuthentication:
    def test_master_key_sent_as_bearer_token(self):
        captured = {}

        def handler(request):
            captured["auth"] = request.headers.get("Authorization")
            return httpx.Response(200, json={"data": []})

        client = build_client(handler)
        client.list_models_v1_info()

        assert captured["auth"] == "Bearer sk-test-master-key"


class TestFromSettings:
    def test_reads_url_and_master_key_from_settings(self, settings):
        settings.AI_GATEWAY_URL = "http://gateway.example"
        settings.AI_GATEWAY_MASTER_KEY = "sk-from-settings"

        client = AIGatewayClient.from_settings()

        assert client._base_url == "http://gateway.example"
        assert client._client.headers["Authorization"] == "Bearer sk-from-settings"

    def test_raises_if_settings_missing(self, settings):
        settings.AI_GATEWAY_URL = ""
        settings.AI_GATEWAY_MASTER_KEY = ""

        with pytest.raises(ImproperlyConfigured) as exc_info:
            AIGatewayClient.from_settings()

        assert "AI_GATEWAY_URL and AI_GATEWAY_MASTER_KEY must be configured" in str(exc_info.value)
