from unittest.mock import patch

import pytest
from django.urls import reverse
from model_bakery import baker
from pytest_django.asserts import (
    assertContains,
    assertInHTML,
    assertNotContains,
    assertTemplateNotUsed,
    assertTemplateUsed,
)

from ai_gateway.exceptions import AIGatewayAPIError
from ai_gateway.models import Key

PLAINTEXT_KEY = "sk-plaintext-key-value-123456"


class TestKeyListView:
    def test_renders_for_member(self, client, user, project):
        client.force_login(user)
        response = client.get(reverse("ai_gateway:key_list", args=[project.uuid]))
        current_ai_gateway_link = (
            f'<a href="{reverse("ai_gateway:key_list", args=[project.uuid])}" '
            'aria-current="location">AI Gateway</a>'
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
    def test_get_renders_form(self, client, user, project, key_service):
        client.force_login(user)
        response = client.get(reverse("ai_gateway:key_create", args=[project.uuid]))

        assert response.status_code == 200
        assertTemplateUsed(response, "ai_gateway/key-create.html")
        assertContains(response, 'data-module="moj-multi-select"')
        assertContains(response, "gpt-4")

    def test_post_redirects_to_confirm_with_params(self, client, user, project, key_service):
        client.force_login(user)

        response = client.post(
            reverse("ai_gateway:key_create", args=[project.uuid]),
            data={"name": "primary-key", "models": ["gpt-4", "claude-3"]},
        )

        assert response.status_code == 302
        confirm_url = reverse("ai_gateway:key_create_confirm", args=[project.uuid])
        assert response.url.startswith(f"{confirm_url}?")
        assert "name=primary-key" in response.url
        assert "models=gpt-4" in response.url
        assert "models=claude-3" in response.url
        key_service.create_key.assert_not_called()
        assert not Key.objects.filter(project=project).exists()

    def test_get_prefills_name_and_selection_from_params(self, client, user, project, key_service):
        client.force_login(user)

        response = client.get(
            reverse("ai_gateway:key_create", args=[project.uuid]),
            data={"name": "primary-key", "models": ["claude-3"]},
        )

        assert response.status_code == 200
        assertContains(response, 'value="primary-key"')
        assertContains(
            response,
            '<input class="govuk-checkboxes__input" id="models-2" '
            'name="models" type="checkbox" value="claude-3" checked>',
            html=True,
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


class TestKeyCreateViewFiltering:
    def test_get_renders_provider_and_family_filters(self, client, user, project, key_service):
        client.force_login(user)

        response = client.get(reverse("ai_gateway:key_create", args=[project.uuid]))

        assertContains(response, 'name="provider"')
        assertContains(response, 'name="family"')
        assertContains(response, "OpenAI")
        assertContains(response, "Anthropic")
        assertContains(response, "GPT")
        assertContains(response, "Claude")

    def test_filters_models_by_provider(self, client, user, project, key_service):
        client.force_login(user)

        response = client.get(
            reverse("ai_gateway:key_create", args=[project.uuid]),
            {"provider": "Anthropic"},
        )

        assertContains(response, 'value="claude-3"')
        assertNotContains(response, 'value="gpt-4"')

    def test_htmx_request_returns_the_fragment_only(self, client, user, project, key_service):
        client.force_login(user)

        response = client.get(
            reverse("ai_gateway:key_create", args=[project.uuid]),
            headers={"HX-Request": "true"},
        )

        assert response.status_code == 200
        assertTemplateUsed(response, "includes/ai_gateway/_model_list.html")
        assertTemplateNotUsed(response, "ai_gateway/key-create.html")
        assertContains(response, 'data-module="moj-multi-select"')

    def test_selection_outside_the_filter_is_kept_as_hidden_input(
        self, client, user, project, key_service
    ):
        client.force_login(user)

        response = client.get(
            reverse("ai_gateway:key_create", args=[project.uuid]),
            {"provider": "Anthropic", "models": ["gpt-4"]},
        )

        assertContains(
            response,
            '<input type="hidden" name="models" value="gpt-4">',
            html=True,
        )
        assertContains(response, 'value="claude-3"')

    def test_show_more_reveals_all_matches(self, client, user, project, key_service):
        key_service.list_available_models.return_value = [
            {
                "model_name": f"model-{index}",
                "display_name": f"Model {index}",
                "family": "Test",
                "provider": "TestProvider",
                "input_cost_per_million": 1.0,
                "output_cost_per_million": 2.0,
            }
            for index in range(12)
        ]
        client.force_login(user)

        collapsed = client.get(reverse("ai_gateway:key_create", args=[project.uuid]))

        assertContains(collapsed, "Show all")
        assertContains(collapsed, 'value="model-0"')
        assertNotContains(collapsed, 'value="model-11"')

        expanded = client.get(
            reverse("ai_gateway:key_create", args=[project.uuid]),
            {"expanded": "1"},
        )

        assertContains(expanded, 'value="model-11"')
        assertNotContains(expanded, "Show all")


class TestKeyCreateConfirmView:
    def _confirm_url(self, project):
        return reverse("ai_gateway:key_create_confirm", args=[project.uuid])

    def test_get_renders_confirmation_page(self, client, user, project, key_service):
        client.force_login(user)

        response = client.get(
            self._confirm_url(project),
            data={"name": "primary-key", "models": ["gpt-4", "claude-3"]},
        )

        assert response.status_code == 200
        assertTemplateUsed(response, "ai_gateway/key-create-confirm.html")
        assertContains(response, "primary-key")
        assertContains(response, "GPT-4")
        assertContains(response, "Claude 3")

    def test_get_without_params_redirects_to_key_create(self, client, user, project, key_service):
        client.force_login(user)

        response = client.get(self._confirm_url(project))

        assert response.status_code == 302
        assert response.url.startswith(reverse("ai_gateway:key_create", args=[project.uuid]))

    def test_get_without_models_redirects_to_key_create(self, client, user, project, key_service):
        client.force_login(user)

        response = client.get(self._confirm_url(project), data={"name": "primary-key"})

        assert response.status_code == 302
        assert response.url.startswith(reverse("ai_gateway:key_create", args=[project.uuid]))

    def test_post_creates_key_and_renders_created_page(self, client, user, project, key_service):
        key_service.create_key.return_value = PLAINTEXT_KEY
        client.force_login(user)

        response = client.post(
            self._confirm_url(project),
            data={"name": "primary-key", "models": ["gpt-4", "claude-3"]},
        )

        assert response.status_code == 200
        assertTemplateUsed(response, "ai_gateway/key-created.html")
        assertContains(response, PLAINTEXT_KEY)
        assert "no-store" in response["Cache-Control"]
        key_service.create_key.assert_called_once_with(
            project=project,
            name="primary-key",
            models=["gpt-4", "claude-3"],
            created_by=user,
        )

    def test_post_without_data_redirects_to_key_create(self, client, user, project, key_service):
        client.force_login(user)

        response = client.post(self._confirm_url(project))

        assert response.status_code == 302
        assert response.url.startswith(reverse("ai_gateway:key_create", args=[project.uuid]))
        key_service.create_key.assert_not_called()

    def test_post_gateway_error_propagates(self, client, user, project, key_service):
        key_service.create_key.side_effect = AIGatewayAPIError(500, "gateway error")
        client.force_login(user)

        with pytest.raises(AIGatewayAPIError):
            client.post(
                self._confirm_url(project),
                data={"name": "primary-key", "models": ["gpt-4"]},
            )

    def test_post_duplicate_name_redirects_to_key_create(
        self, client, user, project, key, key_service
    ):
        client.force_login(user)

        response = client.post(
            self._confirm_url(project),
            data={"name": key.name, "models": ["gpt-4"]},
        )

        assert response.status_code == 302
        assert response.url.startswith(reverse("ai_gateway:key_create", args=[project.uuid]))
        key_service.create_key.assert_not_called()

    def test_non_member_gets_404(self, client, non_project_user, project, key_service):
        client.force_login(non_project_user)

        response = client.get(self._confirm_url(project))

        assert response.status_code == 404


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

    def test_renders_none_when_key_uses_no_default_models(
        self, client, user, project, key, key_service
    ):
        key_service.get_models_for_key.return_value = ["no-default-models"]
        client.force_login(user)

        response = client.get(reverse("ai_gateway:key_detail", args=[project.uuid, key.pk]))

        assert response.status_code == 200
        assertContains(response, "None")
        assertNotContains(response, "no-default-models")

    def test_renders_fallback_message_when_gateway_call_fails(
        self, client, user, project, key, key_service
    ):
        key_service.get_models_for_key.side_effect = AIGatewayAPIError(503, "gateway unavailable")
        client.force_login(user)
        expected_error_message = (
            "Error retrieving models from the AI Gateway. "
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


class TestKeyRegenerateView:
    def test_renders_for_member(self, client, user, project, key):
        client.force_login(user)
        response = client.get(reverse("ai_gateway:key_regenerate", args=[project.uuid, key.pk]))

        assert response.status_code == 200
        assert "ai_gateway/key-regenerate.html" in [t.name for t in response.templates]

    def test_non_member_gets_404(self, client, non_project_user, project, key):
        client.force_login(non_project_user)
        response = client.get(reverse("ai_gateway:key_regenerate", args=[project.uuid, key.pk]))

        assert response.status_code == 404

    def test_post_regenerates_key_and_renders_created_template(
        self, client, user, project, key, key_service
    ):
        client.force_login(user)
        key_service.regenerate_key.return_value = PLAINTEXT_KEY

        response = client.post(reverse("ai_gateway:key_regenerate", args=[project.uuid, key.pk]))

        assert response.status_code == 200
        assertTemplateUsed(response, "ai_gateway/key-created.html")
        assertContains(response, PLAINTEXT_KEY)
        assertContains(response, "Store your API key")
        key_service.regenerate_key.assert_called_once_with(
            key=key,
        )
        assert response.headers["Cache-Control"]

    def test_post_non_member_gets_404(self, client, non_project_user, project, key, key_service):
        client.force_login(non_project_user)

        response = client.post(reverse("ai_gateway:key_regenerate", args=[project.uuid, key.pk]))

        assert response.status_code == 404
        key_service.regenerate_key.assert_not_called()

    def test_post_gateway_error_redirects_to_key_detail_with_error_message(
        self, client, user, project, key, key_service
    ):
        key_service.regenerate_key.side_effect = AIGatewayAPIError(500, "gateway error")
        client.force_login(user)

        with patch("ai_gateway.views.sentry_sdk.capture_exception") as capture_exception:
            response = client.post(
                reverse("ai_gateway:key_regenerate", args=[project.uuid, key.pk])
            )

        assert response.status_code == 302
        assert response.url == reverse("ai_gateway:key_detail", args=[project.uuid, key.pk])
        key.refresh_from_db()
        assert key.litellm_secret == "sk-full-secret"  # unchanged
        capture_exception.assert_called_once()


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
