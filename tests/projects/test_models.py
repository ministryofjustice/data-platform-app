class TestProject:
    """Tests for the `Project` model."""

    def test_get_absolute_url_defaults_to_project_detail(self, project):
        assert project.get_absolute_url() == f"/app/projects/{project.uuid}/"

    def test_get_absolute_keys_url_points_to_ai_gateway_key_list(self, project):
        assert project.get_absolute_keys_url() == f"/app/projects/{project.uuid}/ai-gateway/keys/"
