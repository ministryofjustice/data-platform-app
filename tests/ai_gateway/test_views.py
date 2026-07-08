from unittest.mock import create_autospec, patch

import pytest
from django.urls import reverse

from ai_gateway.exceptions import AIGatewayAPIError
from ai_gateway.models import Key
from ai_gateway.services import KeyService

PLAINTEXT_KEY = "sk-plaintext-key-value-123456"


@pytest.fixture
def key_service():
    """Patch KeyService.from_settings with an autospecced instance used as a context manager."""
    service = create_autospec(KeyService, instance=True)
    service.__enter__.return_value = service
    service.__exit__.return_value = False
    service.list_models.return_value = ["gpt-4", "claude-3"]

    with patch("ai_gateway.views.KeyService.from_settings", return_value=service):
        yield service


class TestKeyListView:
    def test_renders_for_member(self, client, user, project):
        client.force_login(user)
        response = client.get(reverse("ai_gateway:key_list", args=[project.slug]))

        assert response.status_code == 200
        assert "ai_gateway/key-list.html" in [t.name for t in response.templates]

    def test_lists_existing_keys(self, client, user, project, key):
        client.force_login(user)
        response = client.get(reverse("ai_gateway:key_list", args=[project.slug]))

        assert key.masked_key.encode() in response.content

    def test_non_member_gets_404(self, client, non_member, project):
        client.force_login(non_member)
        response = client.get(reverse("ai_gateway:key_list", args=[project.slug]))

        assert response.status_code == 404


class TestKeyCreateView:
    def test_get_renders_form(self, client, user, project, key_service):
        client.force_login(user)
        response = client.get(reverse("ai_gateway:key_create", args=[project.slug]))

        assert response.status_code == 200
        assert "ai_gateway/key-create.html" in [t.name for t in response.templates]
        assert b'data-module="app-multi-select-tags"' in response.content
        assert b"gpt-4" in response.content

    def test_post_shows_plaintext_secret(self, client, user, project, key_service):
        key_service.create_key.return_value = PLAINTEXT_KEY
        client.force_login(user)

        response = client.post(
            reverse("ai_gateway:key_create", args=[project.slug]),
            data={"name": "primary-key", "models": ["gpt-4", "claude-3"]},
        )

        assert response.status_code == 200
        assert "ai_gateway/key-created.html" in [t.name for t in response.templates]
        assert PLAINTEXT_KEY.encode() in response.content
        key_service.create_key.assert_called_once_with(
            project, "primary-key", ["gpt-4", "claude-3"], user
        )

    def test_post_rejects_unknown_model(self, client, user, project, key_service):
        client.force_login(user)

        response = client.post(
            reverse("ai_gateway:key_create", args=[project.slug]),
            data={"name": "primary-key", "models": ["not-a-model"]},
        )

        assert response.status_code == 200
        assert "ai_gateway/key-create.html" in [t.name for t in response.templates]
        key_service.create_key.assert_not_called()

    def test_post_requires_at_least_one_model(self, client, user, project, key_service):
        client.force_login(user)

        response = client.post(
            reverse("ai_gateway:key_create", args=[project.slug]),
            data={"name": "primary-key"},
        )

        assert response.status_code == 200
        assert "ai_gateway/key-create.html" in [t.name for t in response.templates]
        assert not Key.objects.filter(project=project).exists()
        key_service.create_key.assert_not_called()

    def test_post_gateway_error_propagates(self, client, user, project, key_service):
        key_service.create_key.side_effect = AIGatewayAPIError(500, "boom")
        client.force_login(user)

        with pytest.raises(AIGatewayAPIError):
            client.post(
                reverse("ai_gateway:key_create", args=[project.slug]),
                data={"name": "primary-key", "models": ["gpt-4"]},
            )

    def test_post_duplicate_name_returns_form_error_without_calling_service(
        self, client, user, project, key, key_service
    ):
        client.force_login(user)

        response = client.post(
            reverse("ai_gateway:key_create", args=[project.slug]),
            data={"name": key.name, "models": ["gpt-4"]},
        )

        assert response.status_code == 200
        assert b"A key with this name already exists for this project." in response.content
        key_service.create_key.assert_not_called()

    def test_non_member_gets_404(self, client, non_member, project, key_service):
        client.force_login(non_member)

        response = client.post(
            reverse("ai_gateway:key_create", args=[project.slug]),
            data={"name": "primary-key", "models": ["gpt-4"]},
        )

        assert response.status_code == 404
        assert not Key.objects.filter(project=project).exists()
        key_service.create_key.assert_not_called()
