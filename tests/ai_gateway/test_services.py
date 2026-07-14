from datetime import timedelta
from unittest.mock import create_autospec

import pytest
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured

from ai_gateway.client import AIGatewayClient
from ai_gateway.exceptions import AIGatewayAPIError
from ai_gateway.models import Key, Team
from ai_gateway.services import KeyService

PLAINTEXT_KEY = "sk-plaintext-key-value-123456"


@pytest.fixture
def gateway_client():
    """An autospecced AIGatewayClient with default successful responses."""
    client = create_autospec(AIGatewayClient, instance=True)
    client.create_team.return_value = "team-xyz"
    client.generate_key.return_value = {"key": PLAINTEXT_KEY, "token": "tok-1"}
    client.get_access_group_id.return_value = "ag-default"
    return client


@pytest.fixture(autouse=True)
def clear_django_cache():
    cache.clear()
    yield
    cache.clear()


class TestMaskKey:
    def test_masks_a_long_key(self):
        assert KeyService._mask_key("sk-very-long-secret-1234") == "...1234"

    def test_short_key_is_fully_masked(self):
        assert KeyService._mask_key("1234") == "..."


class TestBuildAlias:
    def test_prefixes_project_uuid_and_slugifies_name(self, project):
        alias = KeyService._build_alias(project, "My Special Key")

        assert alias.startswith(f"{project.uuid}-my-special-key-")

    def test_aliases_are_unique_for_the_same_inputs(self, project):
        first = KeyService._build_alias(project, "same-name")
        second = KeyService._build_alias(project, "same-name")

        assert first != second


class TestKeyServiceListModels:
    def test_returns_client_models_for_default_access_group(self, gateway_client, settings):
        settings.DEFAULT_ACCESS_GROUP_NAME = "generally-available-models"
        gateway_client.list_models_for_access_group.return_value = ["gpt-4", "claude-3"]

        with KeyService(gateway_client) as service:
            assert service.list_default_models() == ["gpt-4", "claude-3"]

        gateway_client.list_models_for_access_group.assert_called_once_with(
            "generally-available-models"
        )

    def test_raises_when_default_access_group_is_not_configured(self, gateway_client, settings):
        settings.DEFAULT_ACCESS_GROUP_NAME = None

        with KeyService(gateway_client) as service, pytest.raises(ImproperlyConfigured):
            service.list_default_models()

        gateway_client.list_models_for_access_group.assert_not_called()


class TestKeyServiceCreateKey:
    def test_creates_team_lazily_and_persists_metadata(
        self, project, user, gateway_client, settings
    ):
        settings.DEFAULT_ACCESS_GROUP_NAME = "generally-available-models"
        gateway_client.get_access_group_id.return_value = "ag-default"

        with KeyService(gateway_client) as service:
            plaintext = service.create_key(project, "primary-key", ["gpt-4"], user)

        assert plaintext == PLAINTEXT_KEY
        gateway_client.get_access_group_id.assert_called_once_with("generally-available-models")
        gateway_client.create_team.assert_called_once_with(str(project.uuid), ["ag-default"])
        team = Team.objects.get(project=project)
        assert team.litellm_team_id == "team-xyz"

        gateway_client.generate_key.assert_called_once()
        assert gateway_client.generate_key.call_args.args == ("team-xyz",)
        assert gateway_client.generate_key.call_args.kwargs["models"] == ["gpt-4"]
        alias_sent = gateway_client.generate_key.call_args.kwargs["key_alias"]
        assert alias_sent.startswith(f"{project.uuid}-primary-key-")

        key = Key.objects.get(project=project)
        assert key.name == "primary-key"
        assert key.litellm_alias == alias_sent
        assert key.litellm_secret == PLAINTEXT_KEY
        assert key.litellm_token == "tok-1"
        assert key.masked_key != PLAINTEXT_KEY
        assert PLAINTEXT_KEY not in key.masked_key
        assert key.created_by == user
        gateway_client.close.assert_called_once()

    def test_reuses_existing_team(self, project, user, gateway_client):
        Team.objects.create(project=project, litellm_team_id="existing-team")

        with KeyService(gateway_client) as service:
            service.create_key(project, "primary-key", ["gpt-4"], user)

        gateway_client.create_team.assert_not_called()
        gateway_client.generate_key.assert_called_once()
        assert gateway_client.generate_key.call_args.args == ("existing-team",)
        assert gateway_client.generate_key.call_args.kwargs["key_alias"].startswith(
            f"{project.uuid}-primary-key-"
        )

    def test_slugifies_name_for_gateway_alias(self, project, user, gateway_client):
        with KeyService(gateway_client) as service:
            service.create_key(project, "My Special Key", ["gpt-4"], user)

        alias_sent = gateway_client.generate_key.call_args.kwargs["key_alias"]
        assert alias_sent.startswith(f"{project.uuid}-my-special-key-")

        key = Key.objects.get(project=project)
        assert key.name == "My Special Key"
        assert key.litellm_alias == alias_sent

    def test_gateway_error_propagates_and_stores_no_key(self, project, user, gateway_client):
        gateway_client.generate_key.side_effect = AIGatewayAPIError(500, "boom")

        with pytest.raises(AIGatewayAPIError), KeyService(gateway_client) as service:
            service.create_key(project, "primary-key", ["gpt-4"], user)

        assert not Key.objects.filter(project=project).exists()
        gateway_client.close.assert_called_once()


class TestKeyServiceGetModelsForKey:
    def test_uses_cache_for_repeated_lookup(self, gateway_client, key):
        gateway_client.key_info.return_value = {"info": {"models": ["gpt-4"]}}

        with KeyService(gateway_client) as service:
            first = service.get_models_for_key(key)
            second = service.get_models_for_key(key)

        assert first == ["gpt-4"]
        assert second == ["gpt-4"]
        gateway_client.key_info.assert_called_once_with(key.litellm_secret)

    def test_cache_key_changes_when_key_modified_changes(self, gateway_client, key):
        gateway_client.key_info.side_effect = [
            {"info": {"models": ["gpt-4"]}},
            {"info": {"models": ["claude-3"]}},
        ]

        with KeyService(gateway_client) as service:
            first = service.get_models_for_key(key)

            Key.objects.filter(pk=key.pk).update(modified=key.modified + timedelta(seconds=1))
            key.refresh_from_db(fields=["modified"])

            second = service.get_models_for_key(key)

        assert first == ["gpt-4"]
        assert second == ["claude-3"]
        assert gateway_client.key_info.call_count == 2
