import pytest
from django.urls import reverse

from projects.models import Project, ProjectUserPermissions


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


class TestProjectDeleteView:
    """Tests for the ProjectDeleteView at '/projects/<slug>/delete'."""

    def test_delete_page_renders(self, client, user, project):
        client.force_login(user)
        response = client.get(reverse("projects:project_delete", args=[project.slug]))

        assert response.status_code == 200
        assert "projects/delete-confirm.html" in [t.name for t in response.templates]

    def test_delete_project(self, client, user, project):
        client.force_login(user)
        response = client.post(reverse("projects:project_delete", args=[project.slug]))

        assert response.status_code == 302
        assert not Project.objects.filter(id=project.id).exists()


class TestProjectRemoveUserView:
    """Tests for the ProjectRemoveUserView at '/projects/<slug>/users/<user_id>/remove/'."""

    def test_remove_user_page_renders(self, client, user, project):
        client.force_login(user)
        response = client.get(
            reverse("projects:project_user_remove", args=[project.slug, user.id])
        )

        assert response.status_code == 200
        assert "projects/user-remove-confirm.html" in [t.name for t in response.templates]

    def test_remove_user(self, client, user, project):
        client.force_login(user)
        response = client.post(
            reverse("projects:project_user_remove", args=[project.slug, user.id])
        )

        assert response.status_code == 302
        assert not ProjectUserPermissions.objects.filter(project=project, user=user).exists()
