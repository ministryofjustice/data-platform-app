import pytest
from django.urls import reverse


@pytest.fixture
def project(db, user):
    """A project created by a user."""
    from model_bakery import baker

    project = baker.make(
        "projects.Project", name="Example Project", slug="example-slug", created_by=user
    )

    baker.make("projects.ProjectUserPermissions", project=project, user=user, role="admin")

    return project


class TestListView:
    """Tests for the ProjectListView at '/projects/'."""

    def test_list_page_renders(self, client, user):
        client.force_login(user)
        response = client.get(reverse("projects:projects_list"))

        assert response.status_code == 200
        assert "projects/list.html" in [t.name for t in response.templates]


class TestDetailView:
    """Tests for the ProjectDetailView at '/projects/<slug>/'."""

    def test_detail_page_renders(self, client, user, project):
        client.force_login(user)
        response = client.get(reverse("projects:project_detail", args=[project.slug]))

        assert response.status_code == 200
        assert "projects/detail.html" in [t.name for t in response.templates]
