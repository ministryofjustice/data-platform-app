from django.urls import reverse


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


class TestHealthcheckView:
    """Tests for the healthcheck endpoint at '/healthcheck/'"""

    def test_healthcheck_view(self, client):
        response = client.get(reverse("healthcheck"))

        assert response.status_code == 200
        assert response.content == b"OK"
