from unittest.mock import create_autospec

import pytest

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
    return client


class TestMaskKey:
    def test_masks_a_long_key(self):
        assert KeyService._mask_key("sk-abcdefghijklmnop") == "sk-abc...mnop"

    def test_short_key_is_fully_masked(self):
        assert KeyService._mask_key("sk-123") == "..."


class TestBuildAlias:
    def test_prefixes_project_slug_and_slugifies_name(self, project):
        alias = KeyService._build_alias(project, "My Special Key")

        assert alias.startswith("example-slug-my-special-key-")

    def test_aliases_are_unique_for_the_same_inputs(self, project):
        first = KeyService._build_alias(project, "same-name")
        second = KeyService._build_alias(project, "same-name")

        assert first != second


class TestKeyServiceCreateKey:
    def test_creates_team_lazily_and_persists_metadata(self, project, user, gateway_client):
        with KeyService(gateway_client) as service:
            plaintext = service.create_key(project, "primary-key", user)

        assert plaintext == PLAINTEXT_KEY
        gateway_client.create_team.assert_called_once_with("Example Project")
        team = Team.objects.get(project=project)
        assert team.litellm_team_id == "team-xyz"

        gateway_client.generate_key.assert_called_once()
        assert gateway_client.generate_key.call_args.args == ("team-xyz",)
        alias_sent = gateway_client.generate_key.call_args.kwargs["key_alias"]
        assert alias_sent.startswith("example-slug-primary-key-")

        key = Key.objects.get(project=project)
        assert key.name == "primary-key"
        assert key.litellm_alias == alias_sent
        assert key.litellm_token == "tok-1"
        assert key.masked_key != PLAINTEXT_KEY
        assert PLAINTEXT_KEY not in key.masked_key
        assert key.created_by == user
        gateway_client.close.assert_called_once()

    def test_reuses_existing_team(self, project, user, gateway_client):
        Team.objects.create(project=project, litellm_team_id="existing-team")

        with KeyService(gateway_client) as service:
            service.create_key(project, "primary-key", user)

        gateway_client.create_team.assert_not_called()
        gateway_client.generate_key.assert_called_once()
        assert gateway_client.generate_key.call_args.args == ("existing-team",)
        assert gateway_client.generate_key.call_args.kwargs["key_alias"].startswith(
            "example-slug-primary-key-"
        )

    def test_slugifies_name_for_gateway_alias(self, project, user, gateway_client):
        with KeyService(gateway_client) as service:
            service.create_key(project, "My Special Key", user)

        alias_sent = gateway_client.generate_key.call_args.kwargs["key_alias"]
        assert alias_sent.startswith("example-slug-my-special-key-")

        key = Key.objects.get(project=project)
        assert key.name == "My Special Key"
        assert key.litellm_alias == alias_sent

    def test_gateway_error_propagates_and_stores_no_key(self, project, user, gateway_client):
        gateway_client.generate_key.side_effect = AIGatewayAPIError(500, "boom")

        with pytest.raises(AIGatewayAPIError), KeyService(gateway_client) as service:
            service.create_key(project, "primary-key", user)

        assert not Key.objects.filter(project=project).exists()
        gateway_client.close.assert_called_once()
