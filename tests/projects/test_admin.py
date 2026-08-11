import pytest
from django.urls import reverse
from model_bakery import baker


@pytest.fixture
def superuser(db):
    """A superuser able to access the Django admin."""
    return baker.make("users.User", is_staff=True, is_superuser=True)


class TestProjectAdminTeamInline:
    def test_change_page_links_to_the_projects_team(self, client, superuser, project):
        team = baker.make("ai_gateway.Team", project=project, litellm_team_id="team-abc-123")
        client.force_login(superuser)
        url = reverse("admin:projects_project_change", args=[project.pk])

        response = client.get(url)

        assert response.status_code == 200
        team_url = reverse("admin:ai_gateway_team_change", args=[team.pk])
        assert team_url.encode() in response.content

    def test_change_page_renders_without_a_team(self, client, superuser, project):
        client.force_login(superuser)
        url = reverse("admin:projects_project_change", args=[project.pk])

        response = client.get(url)

        assert response.status_code == 200
