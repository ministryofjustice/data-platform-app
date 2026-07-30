import re

import pytest
from django.urls import reverse
from pytest_django.asserts import assertContains, assertNotContains


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


class TestHealthcheckView:
    """Tests for the healthcheck endpoint at '/healthcheck/'"""

    def test_healthcheck_view(self, client):
        response = client.get(reverse("healthcheck"))

        assert response.status_code == 200
        assert response.content == b"OK"
