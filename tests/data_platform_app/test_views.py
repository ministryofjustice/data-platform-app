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
        assert "service_navigation_items" in response.context


class TestRoadmapView:
    """Tests for the RoadmapView at '/roadmap/'."""

    def test_roadmap_page_renders(self, client):
        response = client.get(reverse("roadmap"))

        assert response.status_code == 200
        assert "roadmap.html" in [t.name for t in response.templates]

    def test_context(self, client):
        response = client.get(reverse("roadmap"))
        assert "service_navigation_items" in response.context


class TestDataFactoriesView:
    """Tests for the DataFactoriesView at '/data-factories/'."""

    def test_data_factories_page_renders(self, client):
        response = client.get(reverse("data_factories"))

        assert response.status_code == 200
        assert "data_factories.html" in [t.name for t in response.templates]

    def test_context(self, client):
        response = client.get(reverse("data_factories"))
        assert "service_navigation_items" in response.context


class TestHealthcheckView:
    """Tests for the healthcheck endpoint at '/healthcheck/'"""

    def test_healthcheck_view(self, client):
        response = client.get(reverse("healthcheck"))

        assert response.status_code == 200
        assert response.content == b"OK"

    def test_healthcheck_with_elb_user_agent(self, client):
        """Test healthcheck with ELB User-Agent header"""
        response = client.get(reverse("healthcheck"), HTTP_USER_AGENT="ELB-HealthChecker/2.0")

        assert response.status_code == 200
        assert response.content == b"OK"

    def test_healthcheck_with_mismatched_host_header(self, client):
        """Test healthcheck with Host header that doesn't match ALLOWED_HOSTS"""
        # Simulate ELB sending a request with an internal IP or non-matching host
        response = client.get(reverse("healthcheck"), HTTP_HOST="10.199.132.60")

        assert response.status_code == 400

    def test_healthcheck_with_elb_headers(self, client):
        """Test healthcheck with realistic ELB request headers"""
        response = client.get(
            reverse("healthcheck"),
            HTTP_HOST="10.199.132.60",
            HTTP_USER_AGENT="ELB-HealthChecker/2.0",
        )

        assert response.status_code == 200
        assert response.content == b"OK"
