from unittest.mock import create_autospec, patch

import pytest
from django.urls import reverse
from pytest_django.asserts import assertContains, assertInHTML, assertTemplateUsed

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
    service.list_default_models.return_value = ["gpt-4", "claude-3"]

    with patch("ai_gateway.views.KeyService.from_settings", return_value=service):
        yield service


class TestKeyListView:
    def test_renders_for_member(self, client, user, project):
        client.force_login(user)
        response = client.get(reverse("ai_gateway:key_list", args=[project.uuid]))
        current_ai_gateway_link = (
            f'<a href="{reverse("ai_gateway:key_list", args=[project.uuid])}" '
            'aria-current="location">AI gateway</a>'
        )

        assert response.status_code == 200
        assert "ai_gateway/key-list.html" in [t.name for t in response.templates]
        assertContains(response, 'aria-current="location"', count=1)
        assertInHTML(current_ai_gateway_link, response.content.decode())

    def test_lists_existing_keys(self, client, user, project, key):
        client.force_login(user)
        response = client.get(reverse("ai_gateway:key_list", args=[project.uuid]))

        assertContains(response, key.litellm_token)

    def test_non_member_gets_404(self, client, non_member, project):
        client.force_login(non_member)
        response = client.get(reverse("ai_gateway:key_list", args=[project.uuid]))

        assert response.status_code == 404


class TestKeyCreateView:
    def test_get_renders_form(self, client, user, project, key_service):
        client.force_login(user)
        response = client.get(reverse("ai_gateway:key_create", args=[project.uuid]))

        assert response.status_code == 200
        assertTemplateUsed(response, "ai_gateway/key-create.html")
        assertContains(response, 'data-module="app-multi-select-tags"')
        assertContains(response, "gpt-4")

    def test_post_shows_plaintext_secret(self, client, user, project, key_service):
        key_service.create_key.return_value = PLAINTEXT_KEY
        client.force_login(user)

        response = client.post(
            reverse("ai_gateway:key_create", args=[project.uuid]),
            data={"name": "primary-key", "models": ["gpt-4", "claude-3"]},
        )

        assert response.status_code == 200
        assertTemplateUsed(response, "ai_gateway/key-created.html")
        assertContains(response, PLAINTEXT_KEY)
        key_service.create_key.assert_called_once_with(
            project, "primary-key", ["gpt-4", "claude-3"], user
        )

    def test_post_rejects_unknown_model(self, client, user, project, key_service):
        client.force_login(user)

        response = client.post(
            reverse("ai_gateway:key_create", args=[project.uuid]),
            data={"name": "primary-key", "models": ["not-a-model"]},
        )

        assert response.status_code == 200
        assertTemplateUsed(response, "ai_gateway/key-create.html")
        key_service.create_key.assert_not_called()

    def test_post_requires_at_least_one_model(self, client, user, project, key_service):
        client.force_login(user)

        response = client.post(
            reverse("ai_gateway:key_create", args=[project.uuid]),
            data={"name": "primary-key"},
        )

        assert response.status_code == 200
        assertTemplateUsed(response, "ai_gateway/key-create.html")
        assert not Key.objects.filter(project=project).exists()
        key_service.create_key.assert_not_called()

    def test_post_gateway_error_propagates(self, client, user, project, key_service):
        key_service.create_key.side_effect = AIGatewayAPIError(500, "boom")
        client.force_login(user)

        with pytest.raises(AIGatewayAPIError):
            client.post(
                reverse("ai_gateway:key_create", args=[project.uuid]),
                data={"name": "primary-key", "models": ["gpt-4"]},
            )

    def test_post_duplicate_name_returns_form_error_without_calling_service(
        self, client, user, project, key, key_service
    ):
        client.force_login(user)

        response = client.post(
            reverse("ai_gateway:key_create", args=[project.uuid]),
            data={"name": key.name, "models": ["gpt-4"]},
        )

        assert response.status_code == 200
        assertContains(response, "A key with this name already exists for this project.")
        key_service.create_key.assert_not_called()

    def test_non_member_gets_404(self, client, non_member, project, key_service):
        client.force_login(non_member)

        response = client.post(
            reverse("ai_gateway:key_create", args=[project.uuid]),
            data={"name": "primary-key", "models": ["gpt-4"]},
        )

        assert response.status_code == 404
        assert not Key.objects.filter(project=project).exists()
        key_service.create_key.assert_not_called()
