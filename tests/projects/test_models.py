from projects.models import Project


class TestProject:
    """Tests for the `Project` model."""

    def test_project_id(self, project):
        """The project ID is displayed on the project detail page."""
        assert project.public_id.startswith("prj-")

    def test_get_by_public_id(self, project):
        """The get_by_public_id method returns the correct project."""
        public_id = project.public_id
        retrieved_project = Project.get_by_public_id(public_id)
        assert retrieved_project == project

    def test_get_absolute_url_defaults_to_project_detail(self, project):
        assert project.get_absolute_url() == f"/app/projects/{project.uuid}/"

    def test_get_absolute_keys_url_points_to_ai_gateway_key_list(self, project):
        assert project.get_absolute_keys_url() == f"/app/projects/{project.uuid}/ai-gateway/keys/"
