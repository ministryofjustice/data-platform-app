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

    def test_authenticated_user_sees_go_to_app_link(self, client, user):
        client.force_login(user)

        response = client.get(reverse("home"))

        assert response.status_code == 200
        assert b"Go to app" in response.content

    def test_anonymous_user_does_not_see_go_to_app_link(self, client):
        response = client.get(reverse("home"))

        assert response.status_code == 200
        assert b"Go to app" not in response.content


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

    def test_authenticated_user_sees_go_to_app_link(self, client, user):
        client.force_login(user)

        response = client.get(reverse("roadmap"))

        assert response.status_code == 200
        assert b"Go to app" in response.content


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

    def test_authenticated_user_sees_go_to_app_link(self, client, user):
        client.force_login(user)

        response = client.get(reverse("data_factories"))

        assert response.status_code == 200
        assert b"Go to app" in response.content


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

    def test_authenticated_user_does_not_see_go_to_app_link(self, client, user):
        client.force_login(user)

        response = client.get(reverse("landing"))

        assert response.status_code == 200
        assert b"Go to app" not in response.content


class TestHealthcheckView:
    """Tests for the healthcheck endpoint at '/healthcheck/'"""

    def test_healthcheck_view(self, client):
        response = client.get(reverse("healthcheck"))

        assert response.status_code == 200
        assert response.content == b"OK"
