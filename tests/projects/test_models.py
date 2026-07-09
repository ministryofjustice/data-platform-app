import pytest
from model_bakery import baker

from projects.models import Project


@pytest.fixture
def project(db, user):
    """A project created by a user."""

    project = baker.make(
        "projects.Project", name="Example Project", slug="example-slug", created_by=user
    )

    baker.make("projects.ProjectUserPermissions", project=project, user=user, role="admin")

    return project


class TestProject:
    """Tests for the ProjectDetailView at '/projects/<slug>/'."""

    def test_project_id(self, project):
        """The project ID is displayed on the project detail page."""
        assert project.public_id.startswith("prj-")

    def test_get_by_public_id(self, project):
        """The get_by_public_id method returns the correct project."""
        public_id = project.public_id
        retrieved_project = Project.get_by_public_id(public_id)
        assert retrieved_project == project
