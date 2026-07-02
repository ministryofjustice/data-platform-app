from django.urls import reverse


class TestProjectsListView:
    """Tests for the login-protected projects ListView."""

    def test_redirects_anonymous_user_to_login(self, client):
        response = client.get(reverse("projects:projects_list"))

        assert response.status_code == 302
        assert response.url.startswith(reverse("login"))

    def test_renders_for_authenticated_user(self, client, user):
        client.force_login(user)

        response = client.get(reverse("projects:projects_list"))

        assert response.status_code == 200
