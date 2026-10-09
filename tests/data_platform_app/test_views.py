import re
from unittest.mock import patch

import pytest
from django.urls import reverse
from pytest_django.asserts import assertContains, assertNotContains, assertTemplateUsed

from ai_gateway.exceptions import AIGatewayAPIError


def _assert_header_logo_links_to(response, expected_href):
    content = response.content.decode()
    pattern = r'<a\s+class="moj-header__link"\s+href="' + re.escape(expected_href) + r'"'
    assert re.search(pattern, content), f"Header logo does not link to {expected_href!r}"


class TestHomeView:
    """Tests for the HomeView at '/'."""

    def test_home_page_renders(self, client):
        response = client.get(reverse("home"))

        assert response.status_code == 200
        assert "home.html" in [t.name for t in response.templates]

    def test_context(self, client):
        response = client.get(reverse("home"))

        assert response.context["show_masthead"] is True
        assert response.context["inverse_header"] is True
        assert "service_navigation_items" in response.context

    def test_get_started_button_links_to_landing(self, client):
        response = client.get(reverse("home"))

        assertContains(response, f'href="{reverse("landing")}">Get started')

    def test_header_links_to_home_on_product_page(self, client):
        response = client.get(reverse("home"))

        _assert_header_logo_links_to(response, reverse("home"))

    def test_footer_has_no_app_only_links_on_product_page(self, client):
        response = client.get(reverse("home"))

        assertNotContains(response, "About Justice Data Platform")

    def test_footer_displays_application_metadata(self, client, settings):
        settings.APPLICATION_VERSION = "v4.1.0"
        settings.COMMIT_SHA = "abc123def456"

        response = client.get(reverse("home"))

        assertContains(response, "Data Platform Application version v4.1.0")
        assertContains(
            response,
            'href="https://github.com/ministryofjustice/data-platform-app/commit/'
            'abc123def456">abc123def456</a>',
        )


class TestRoadmapView:
    """Tests for the RoadmapView at '/roadmap/'."""

    def test_roadmap_page_renders(self, client):
        response = client.get(reverse("roadmap"))

        assert response.status_code == 200
        assert "roadmap.html" in [t.name for t in response.templates]

    def test_context(self, client):
        response = client.get(reverse("roadmap"))
        assert response.context["show_masthead"] is False
        assert response.context["inverse_header"] is True
        assert "service_navigation_items" in response.context


class TestDataFactoriesView:
    """Tests for the DataFactoriesView at '/data-factories/'."""

    def test_data_factories_page_renders(self, client):
        response = client.get(reverse("data_factories"))

        assert response.status_code == 200
        assert "data_factories.html" in [t.name for t in response.templates]

    def test_context(self, client):
        response = client.get(reverse("data_factories"))
        assert response.context["show_masthead"] is False
        assert response.context["inverse_header"] is True
        assert "service_navigation_items" in response.context


class TestAccessibilityStatementView:
    """Tests for the AccessibilityStatementView at '/accessibility-statement/'."""

    def test_page_renders(self, client):
        response = client.get(reverse("accessibility_statement"))

        assert response.status_code == 200
        assert "accessibility_statement.html" in [t.name for t in response.templates]

    def test_accessible_without_login(self, client):
        response = client.get(reverse("accessibility_statement"))

        assert response.status_code == 200


class TestLandingView:
    """Tests for the login-protected LandingView."""

    def test_redirects_anonymous_user_to_login(self, client):
        response = client.get(reverse("landing"))

        assert response.status_code == 302
        assert response.url.startswith(reverse("login"))

    def test_renders_for_authenticated_user(self, client, user):
        client.force_login(user)

        response = client.get(reverse("landing"))

        assert response.status_code == 200
        assert "landing.html" in [t.name for t in response.templates]

    def test_header_links_to_landing_not_home(self, client, user):
        client.force_login(user)

        response = client.get(reverse("landing"))

        _assert_header_logo_links_to(response, reverse("landing"))

    def test_footer_links_back_to_product_page(self, client, user):
        client.force_login(user)

        response = client.get(reverse("landing"))

        assertContains(response, f'href="{reverse("home")}">About Justice Data Platform')

    @pytest.mark.skip(reason="Footer link to accessibility statement removed for now")
    def test_footer_links_to_accessibility_statement(self, client, user):
        client.force_login(user)

        response = client.get(reverse("landing"))

        assertContains(
            response,
            f'href="{reverse("accessibility_statement")}">Accessibility',
        )

    def test_top_nav_includes_user_guide_link(self, client, user):
        client.force_login(user)

        response = client.get(reverse("landing"))

        assertContains(
            response,
            'href="https://user-guide.data-platform.service.justice.gov.uk/"',
        )

    def test_links_to_ai_cost_usage_calculator(self, client, user):
        client.force_login(user)

        response = client.get(reverse("landing"))

        assertContains(response, f'href="{reverse("ai_cost_usage_calculator")}"')

    def test_links_to_ai_model_availability(self, client, user):
        client.force_login(user)

        response = client.get(reverse("landing"))

        assertContains(response, "Justice AI Gateway tools")
        assertContains(response, "Browse models available on the Justice AI Gateway")
        assertContains(response, f'href="{reverse("ai_model_availability")}"')

    def test_links_to_find_moj_data(self, client, user):
        client.force_login(user)

        response = client.get(reverse("landing"))

        assertContains(response, 'href="https://find-moj-data.service.justice.gov.uk/"')


class TestAICostUsageCalculatorView:
    """Tests for the login-protected AICostUsageCalculatorView."""

    def test_redirects_anonymous_user_to_login(self, client):
        response = client.get(reverse("ai_cost_usage_calculator"))

        assert response.status_code == 302
        assert response.url.startswith(reverse("login"))

    def test_renders_for_authenticated_user(self, client, user, key_service):
        client.force_login(user)

        response = client.get(reverse("ai_cost_usage_calculator"))

        assert response.status_code == 200
        assert "ai_gateway/ai_cost_usage_calculator.html" in [t.name for t in response.templates]


class TestAIModelAvailabilityView:
    def test_redirects_anonymous_user_to_login(self, client):
        response = client.get(reverse("ai_model_availability"))

        assert response.status_code == 302
        assert response.url.startswith(reverse("login"))

    def test_renders_model_catalogue(self, client, user, key_service):
        key_service.list_all_models.return_value = [
            {
                "model_name": "gpt-4",
                "display_name": "GPT-4",
                "provider": "OpenAI",
                "generally_available": True,
                "region": "United Kingdom",
            },
            {
                "model_name": "claude-3",
                "display_name": "Claude 3",
                "provider": "Anthropic",
                "generally_available": False,
                "region": "European Union",
            },
        ]
        client.force_login(user)

        response = client.get(reverse("ai_model_availability"))

        assert response.status_code == 200
        assertContains(response, "AI model availability")
        assertContains(response, "2 models</strong>")
        assertContains(response, "GPT-4")
        assertContains(response, "OpenAI")
        assertContains(response, "Available")
        assertContains(response, "By request")
        assertContains(response, "European Union")
        assertContains(response, 'name="search"')
        assertContains(response, 'name="provider"')
        assertContains(response, 'name="region"')
        assertContains(response, 'data-module="moj-sortable-table"')

    def test_filters_models_by_search_provider_and_region(self, client, user, key_service):
        key_service.list_all_models.return_value = [
            {
                "model_name": "gpt-4",
                "display_name": "GPT-4",
                "provider": "OpenAI",
                "generally_available": True,
                "region": "United Kingdom",
            },
            {
                "model_name": "claude-3",
                "display_name": "Claude 3",
                "provider": "Anthropic",
                "generally_available": False,
                "region": "European Union",
            },
        ]
        client.force_login(user)

        response = client.get(
            reverse("ai_model_availability"),
            {"search": "claude", "provider": "Anthropic", "region": "European Union"},
        )

        assert response.status_code == 200
        assertContains(response, "Claude 3")
        assertContains(response, "1 model</strong>")
        assertNotContains(response, "GPT-4")

    def test_htmx_request_returns_results_fragment(self, client, user, key_service):
        key_service.list_all_models.return_value = [
            {
                "model_name": "gpt-4",
                "display_name": "GPT-4",
                "provider": "OpenAI",
                "generally_available": True,
                "region": "United Kingdom",
            },
        ]
        client.force_login(user)

        response = client.get(
            reverse("ai_model_availability"),
            {"region": "United Kingdom"},
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 200
        assertTemplateUsed(response, "ai_gateway/partials/model-availability-results.html")
        assertContains(response, "GPT-4")
        assertNotContains(response, "AI model availability")

    def test_displays_error_when_gateway_is_unavailable(self, client, user, key_service):
        key_service.list_all_models.side_effect = AIGatewayAPIError(503, "unavailable")
        client.force_login(user)

        with patch("ai_gateway.views.sentry_sdk.capture_exception") as capture_exception:
            response = client.get(reverse("ai_model_availability"))

        assert response.status_code == 200
        assertContains(response, "Model availability is temporarily unavailable")
        assertContains(response, "0 models</strong>")
        capture_exception.assert_called_once()


class TestHealthcheckView:
    """Tests for the healthcheck endpoint at '/healthcheck/'"""

    def test_healthcheck_view(self, client):
        response = client.get(reverse("healthcheck"))

        assert response.status_code == 200
        assert response.content == b"OK"
