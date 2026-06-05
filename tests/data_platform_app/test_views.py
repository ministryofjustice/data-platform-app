import pytest
from django.urls import reverse


@pytest.mark.django_db
class TestHomeView:
    """Tests for the HomeView at '/'."""

    def test_home_page_returns_200(self, client):
        response = client.get(reverse("home"))

        assert response.status_code == 200

    def test_home_page_uses_correct_template(self, client):
        response = client.get(reverse("home"))

        assert "home.html" in [t.name for t in response.templates]

    def test_home_page_sets_show_masthead_in_context(self, client):
        response = client.get(reverse("home"))

        assert response.context["show_masthead"] is True

    def test_home_page_includes_service_navigation_in_context(self, client):
        response = client.get(reverse("home"))

        assert "service_navigation_items" in response.context
