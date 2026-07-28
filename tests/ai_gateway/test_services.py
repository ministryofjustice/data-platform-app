from datetime import timedelta
from unittest.mock import create_autospec

import pytest
from django.core.cache import cache

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
    client.regenerate_key.return_value = "sk-regenerated-key-value-9999"
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
    def test_returns_generally_available_models_with_costs(self, gateway_client):
        gateway_client.list_models_v1_info.return_value = [
            {
                "model_name": "gpt-4",
                "litellm_params": {KeyService.GENERALLY_AVAILABLE_KEY: True},
                "model_info": {
                    "input_cost_per_token": 0.00003,
                    "output_cost_per_token": 0.00006,
                },
            },
            {
                "model_name": "internal-only",
                "litellm_params": {KeyService.GENERALLY_AVAILABLE_KEY: False},
                "model_info": {},
            },
        ]

        with KeyService(gateway_client) as service:
            models = service.list_default_models()

        assert [model["model_name"] for model in models] == ["gpt-4"]
        assert models[0]["input_cost_per_million"] == pytest.approx(30.0)
        assert models[0]["output_cost_per_million"] == pytest.approx(60.0)

    def test_enriches_models_with_display_fields(self, gateway_client):
        gateway_client.list_models_v1_info.return_value = [
            {
                "model_name": "gpt-4",
                "litellm_params": {
                    KeyService.GENERALLY_AVAILABLE_KEY: True,
                    "ai_model_name": "GPT-4",
                    "ai_model_family": "GPT",
                    "ai_model_provider": "OpenAI",
                },
                "model_info": {},
            },
            {
                "model_name": "bare-model",
                "litellm_params": {KeyService.GENERALLY_AVAILABLE_KEY: True},
                "model_info": {},
            },
        ]

        with KeyService(gateway_client) as service:
            models = service.list_default_models()

        assert models[0]["display_name"] == "GPT-4"
        assert models[0]["family"] == "GPT"
        assert models[0]["provider"] == "OpenAI"
        assert models[1]["display_name"] == "bare-model"

    def test_costs_are_none_when_pricing_is_missing(self, gateway_client):
        gateway_client.list_models_v1_info.return_value = [
            {
                "model_name": "gpt-4",
                "litellm_params": {KeyService.GENERALLY_AVAILABLE_KEY: True},
                "model_info": {},
            },
        ]

        with KeyService(gateway_client) as service:
            models = service.list_default_models()

        assert models[0]["input_cost_per_million"] is None
        assert models[0]["output_cost_per_million"] is None

    def test_excludes_models_not_generally_available(self, gateway_client):
        gateway_client.list_models_v1_info.return_value = [
            {
                "model_name": "internal-only",
                "litellm_params": {KeyService.GENERALLY_AVAILABLE_KEY: False},
                "model_info": {},
            },
        ]

        with KeyService(gateway_client) as service:
            assert service.list_default_models() == []


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


class TestKeyServiceRegenerateKey:
    def test_regenerates_and_persists_secret_and_mask(self, project, user, gateway_client):
        key = Key.objects.create(
            project=project,
            name="primary-key",
            litellm_alias=f"{project.uuid}-primary-key-seed",
            litellm_secret="sk-old-secret",
            litellm_token="tok-1",
            masked_key="...secret",
            created_by=user,
        )

        with KeyService(gateway_client) as service:
            plaintext = service.regenerate_key(key)

        key.refresh_from_db()
        assert plaintext == "sk-regenerated-key-value-9999"
        assert key.litellm_secret == "sk-regenerated-key-value-9999"
        assert key.masked_key == "...9999"
        gateway_client.regenerate_key.assert_called_once_with("sk-old-secret")

    def test_raises_when_key_row_is_missing(self, project, gateway_client):
        with KeyService(gateway_client) as service, pytest.raises(Key.DoesNotExist):
            service.regenerate_key(
                Key(
                    pk=9999,
                    project=project,
                    name="bad_key",
                    litellm_alias="alias",
                    litellm_secret="sk-1234",
                    litellm_token="bad_token",
                    masked_key="...bad_key",
                    created_by=None,
                )
            )


class TestKeyServiceDeleteKey:
    def test_deletes_gateway_key_and_object(self, gateway_client, key):
        with KeyService(gateway_client) as service:
            service.delete_key(key)

        gateway_client.delete_key.assert_called_once_with(key.litellm_secret)
        assert not Key.objects.filter(pk=key.pk).exists()


class TestKeyServiceBulkDeleteKeys:
    def test_delegates_to_client(self, gateway_client):
        keys = ["sk-key-one", "sk-key-two", "sk-key-three"]

        with KeyService(gateway_client) as service:
            service.bulk_delete_keys(keys)

        gateway_client.bulk_delete_keys.assert_called_once_with(keys)

    def test_empty_list(self, gateway_client):
        with KeyService(gateway_client) as service:
            service.bulk_delete_keys([])

        gateway_client.bulk_delete_keys.assert_not_called()

    def test_gateway_error_propagates(self, gateway_client):
        gateway_client.bulk_delete_keys.side_effect = AIGatewayAPIError(500, "boom")

        with pytest.raises(AIGatewayAPIError), KeyService(gateway_client) as service:
            service.bulk_delete_keys(["sk-key-one"])


class TestKeyServiceDeleteTeam:
    def test_delegates_to_client(self, gateway_client):
        with KeyService(gateway_client) as service:
            service.delete_team("team-abc-123")

        gateway_client.delete_team.assert_called_once_with("team-abc-123")

    def test_gateway_error_propagates(self, gateway_client):
        gateway_client.delete_team.side_effect = AIGatewayAPIError(404, "team not found")

        with pytest.raises(AIGatewayAPIError), KeyService(gateway_client) as service:
            service.delete_team("team-abc-123")
