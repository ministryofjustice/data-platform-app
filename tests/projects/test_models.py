from projects.models import ProjectPermission


class TestProject:
    """Tests for the `Project` model."""

    def test_get_absolute_url_defaults_to_project_detail(self, project):
        assert project.get_absolute_url() == f"/app/projects/{project.uuid}/"

    def test_get_absolute_keys_url_points_to_ai_gateway_key_list(self, project):
        assert project.get_absolute_keys_url() == f"/app/projects/{project.uuid}/ai-gateway/keys/"


class TestProjectMembership:
    def test_permissions_display_string(self, project, project_member, grant_project_permission):
        grant_project_permission(project, project_member, ProjectPermission.MANAGE_MEMBERS)
        grant_project_permission(project, project_member, ProjectPermission.MANAGE_API_KEYS)
        membership = project_member.project_memberships.get(project=project)
        assert membership.permissions_display_string() == "Manage API keys, manage members"
