from unittest.mock import create_autospec, patch

import pytest
from django.urls import reverse
from model_bakery import baker
from pytest_django.asserts import assertContains, assertInHTML, assertTemplateUsed

from ai_gateway.exceptions import AIGatewayAPIError
from ai_gateway.models import Key
from ai_gateway.services import KeyService
from ai_gateway.views import KeyCreateView

PLAINTEXT_KEY = "sk-plaintext-key-value-123456"


@pytest.fixture
def key_service():
    """Patch KeyService.from_settings with an autospecced instance used as a context manager."""
    service = create_autospec(KeyService, instance=True)
    service.__enter__.return_value = service
    service.__exit__.return_value = False
    service.list_selectable_models_for_key.return_value = [
        {
            "model_name": "gpt-4",
            "litellm_params": {
                "ai_model_name": "gpt-4",
                "ai_model_provider": "OpenAI",
            },
        },
        {
            "model_name": "claude-3",
            "litellm_params": {
                "ai_model_name": "claude-3",
                "ai_model_provider": "Anthropic",
            },
        },
    ]
    service.get_models_for_key.return_value = ["gpt-4"]

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

    def test_lists_manage_link_to_key_detail(self, client, user, project, key):
        client.force_login(user)

        response = client.get(reverse("ai_gateway:key_list", args=[project.uuid]))

        assertContains(
            response,
            f'href="{reverse("ai_gateway:key_detail", args=[project.uuid, key.pk])}"',
        )

    def test_non_member_gets_404(self, client, non_project_user, project):
        client.force_login(non_project_user)
        response = client.get(reverse("ai_gateway:key_list", args=[project.uuid]))

        assert response.status_code == 404


class TestKeyCreateView:
    def test_debug_models_do_not_overlap_with_seeded_gateway_models(self):
        seeded_model_names = {
            "bedrock-claude-sonnet-5",
            "bedrock-claude-opus-4-8",
        }

        debug_model_names = {model["model_name"] for model in KeyCreateView._debug_extra_models()}

        assert debug_model_names.isdisjoint(seeded_model_names)

    def test_get_renders_form(self, client, user, project, key_service):
        client.force_login(user)
        response = client.get(reverse("ai_gateway:key_create", args=[project.uuid]))

        assert response.status_code == 200
        assertTemplateUsed(response, "ai_gateway/key-create.html")
        assertContains(response, 'data-module="app-model-table-filter"')
        assertContains(response, 'data-module="moj-multi-select"')
        assertContains(response, "Search by name")
        assertContains(response, "Filter by provider")
        assertContains(response, "All providers")
        assertContains(response, "gpt-4")
        assertContains(response, "OpenAI")

    def test_get_applies_server_side_filters(self, client, user, project, key_service):
        client.force_login(user)

        response = client.get(
            reverse("ai_gateway:key_create", args=[project.uuid]),
            data={"model_name": "claude", "model_provider": "anthropic", "name": "my key"},
        )

        assert response.status_code == 200
        content = response.content.decode()
        assert "claude-3" in content
        assert "gpt-4" not in content
        assert 'value="claude"' in content
        assert 'value="my key"' in content
        assertInHTML(
            '<option value="anthropic" selected>Anthropic</option>',
            content,
        )

    def test_post_renders_created_page(self, client, user, project, key_service):
        key_service.create_key.return_value = PLAINTEXT_KEY
        client.force_login(user)

        response = client.post(
            reverse("ai_gateway:key_create", args=[project.uuid]),
            data={"name": "primary-key", "models": ["gpt-4", "claude-3"]},
        )

        assert response.status_code == 200
        assertTemplateUsed(response, "ai_gateway/key-created.html")
        assertContains(response, PLAINTEXT_KEY)
        assert "no-store" in response["Cache-Control"]
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

    def test_non_member_gets_404(self, client, non_project_user, project, key_service):
        client.force_login(non_project_user)

        response = client.post(
            reverse("ai_gateway:key_create", args=[project.uuid]),
            data={"name": "primary-key", "models": ["gpt-4"]},
        )

        assert response.status_code == 404
        assert not Key.objects.filter(project=project).exists()
        key_service.create_key.assert_not_called()


class TestKeyDetailView:
    def test_renders_for_member(self, client, user, project, key, key_service):
        client.force_login(user)

        response = client.get(reverse("ai_gateway:key_detail", args=[project.uuid, key.pk]))

        assert response.status_code == 200
        assertTemplateUsed(response, "ai_gateway/key-detail.html")
        assertContains(response, key.name)
        assertContains(response, key.litellm_token)
        assertContains(response, "gpt-4")
        assertContains(
            response,
            f'href="{reverse("ai_gateway:key_revoke", args=[project.uuid, key.pk])}"',
        )

    def test_renders_fallback_message_when_gateway_call_fails(
        self, client, user, project, key, key_service
    ):
        key_service.get_models_for_key.side_effect = AIGatewayAPIError(503, "gateway unavailable")
        client.force_login(user)
        expected_error_message = (
            "Error retrieving models from the AI gateway. "
            "Please contact support if the issue persists."
        )

        with patch("ai_gateway.views.sentry_sdk.capture_exception") as capture_exception:
            response = client.get(reverse("ai_gateway:key_detail", args=[project.uuid, key.pk]))

        assert response.status_code == 200
        assertContains(response, expected_error_message)
        capture_exception.assert_called_once()

    def test_non_member_gets_404(self, client, non_project_user, project, key):
        client.force_login(non_project_user)

        response = client.get(reverse("ai_gateway:key_detail", args=[project.uuid, key.pk]))

        assert response.status_code == 404

    def test_key_from_another_project_gets_404(self, client, user, project):
        other_project = baker.make("projects.Project", created_by=user)
        baker.make(
            "projects.ProjectUserPermissions",
            project=other_project,
            user=user,
            role="admin",
        )
        other_key = baker.make(
            "ai_gateway.Key",
            project=other_project,
            name="other-project-key",
            litellm_secret="sk-other-project-secret",
            litellm_alias="alias-other-project-key",
            litellm_token="token-other-project-key",
            masked_key="sk-oth...key",
            created_by=user,
        )
        client.force_login(user)

        response = client.get(reverse("ai_gateway:key_detail", args=[project.uuid, other_key.pk]))

        assert response.status_code == 404


class TestKeyRevokeView:
    def test_get_renders_confirmation_page(self, client, user, project, key, key_service):
        client.force_login(user)

        response = client.get(reverse("ai_gateway:key_revoke", args=[project.uuid, key.pk]))

        assert response.status_code == 200
        assertTemplateUsed(response, "ai_gateway/key-revoke.html")
        assertContains(response, "Are you sure you want to revoke this API key?")

    def test_post_revokes_key_and_redirects_to_key_list(
        self, client, user, project, key, key_service
    ):
        client.force_login(user)

        response = client.post(reverse("ai_gateway:key_revoke", args=[project.uuid, key.pk]))

        assert response.status_code == 302
        assert response.url == reverse("ai_gateway:key_list", args=[project.uuid])
        key_service.delete_key.assert_called_once_with(key)
        assert client.session["success_message"] == {
            "heading": "Key revoked",
            "message": f"You've revoked {key.name}",
        }

    def test_non_member_gets_404(self, client, non_project_user, project, key, key_service):
        client.force_login(non_project_user)

        get_response = client.get(reverse("ai_gateway:key_revoke", args=[project.uuid, key.pk]))
        post_response = client.post(reverse("ai_gateway:key_revoke", args=[project.uuid, key.pk]))

        assert get_response.status_code == 404
        assert post_response.status_code == 404
        key_service.delete_key.assert_not_called()

    def test_key_from_another_project_gets_404(self, client, user, project, key_service):
        other_project = baker.make("projects.Project", created_by=user)
        baker.make(
            "projects.ProjectUserPermissions",
            project=other_project,
            user=user,
            role="admin",
        )
        other_key = baker.make(
            "ai_gateway.Key",
            project=other_project,
            name="other-project-key",
            litellm_secret="sk-other-project-secret",
            litellm_alias="alias-other-project-key",
            litellm_token="token-other-project-key",
            masked_key="sk-oth...key",
            created_by=user,
        )
        client.force_login(user)

        get_response = client.get(
            reverse("ai_gateway:key_revoke", args=[project.uuid, other_key.pk])
        )
        post_response = client.post(
            reverse("ai_gateway:key_revoke", args=[project.uuid, other_key.pk])
        )

        assert get_response.status_code == 404
        assert post_response.status_code == 404
        key_service.delete_key.assert_not_called()
