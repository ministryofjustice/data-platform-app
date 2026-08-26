"""Tests for MCP resource readers."""

import json
import uuid

import pytest

from ai_gateway.models import Key, Team
from mcp.resources import OperationalDataReader
from projects.models import BusinessUnit, Project, ProjectUserPermissions


@pytest.mark.django_db
class TestOperationalDataReader:
    """Tests for OperationalDataReader."""

    @pytest.fixture
    def admin_user(self, db):
        """Create an admin user."""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        return User.objects.create_user(
            oid=uuid.uuid4(),
            email="admin@example.com",
            is_staff=True,
            is_superuser=True,
        )

    @pytest.fixture
    def regular_user(self, db):
        """Create a regular user."""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        return User.objects.create_user(
            oid=uuid.uuid4(),
            email="user@example.com",
            is_staff=False,
            is_superuser=False,
        )

    @pytest.fixture
    def business_unit(self, db):
        """Create a business unit."""
        return BusinessUnit.objects.create(
            name="Test BU",
            code="TBU",
        )

    @pytest.fixture
    def projects(self, db, admin_user, business_unit):
        """Create test projects."""
        p1 = Project.objects.create(
            name="Project 1",
            description="First project",
            business_unit=business_unit,
            created_by=admin_user,
        )
        p2 = Project.objects.create(
            name="Project 2",
            description="Second project",
            business_unit=business_unit,
            created_by=admin_user,
        )
        return [p1, p2]

    def test_read_projects_superuser_sees_all(self, admin_user, projects):
        """Superuser should see all projects."""
        reader = OperationalDataReader(admin_user)
        result = reader.read_projects()
        data = json.loads(result)
        
        assert len(data["projects"]) == 2
        project_names = {p["name"] for p in data["projects"]}
        assert "Project 1" in project_names
        assert "Project 2" in project_names

    def test_read_projects_member_sees_only_assigned(
        self, db, regular_user, projects
    ):
        """Members should only see projects they're assigned to."""
        ProjectUserPermissions.objects.create(
            project=projects[0],
            user=regular_user,
            role="member",
        )
        
        reader = OperationalDataReader(regular_user)
        result = reader.read_projects()
        data = json.loads(result)
        
        assert len(data["projects"]) == 1
        assert data["projects"][0]["name"] == "Project 1"

    def test_read_projects_includes_metadata(self, admin_user, projects):
        """Project data should include all metadata."""
        reader = OperationalDataReader(admin_user)
        result = reader.read_projects()
        data = json.loads(result)
        
        project = data["projects"][0]
        assert "id" in project
        assert "name" in project
        assert "description" in project
        assert "created" in project
        assert "modified" in project

    def test_read_teams_for_projects(self, db, admin_user, projects):
        """Should read teams for accessible projects."""
        team1 = Team.objects.create(
            project=projects[0],
            litellm_team_id="team-1",
        )
        team2 = Team.objects.create(
            project=projects[1],
            litellm_team_id="team-2",
        )
        
        reader = OperationalDataReader(admin_user)
        result = reader.read_teams()
        data = json.loads(result)
        
        assert len(data["teams"]) == 2
        team_ids = {t["litellm_team_id"] for t in data["teams"]}
        assert "team-1" in team_ids
        assert "team-2" in team_ids

    def test_read_teams_member_only_sees_assigned_projects(
        self, db, regular_user, projects
    ):
        """Members should only see teams from their projects."""
        team1 = Team.objects.create(
            project=projects[0],
            litellm_team_id="team-1",
        )
        team2 = Team.objects.create(
            project=projects[1],
            litellm_team_id="team-2",
        )
        
        ProjectUserPermissions.objects.create(
            project=projects[0],
            user=regular_user,
            role="member",
        )
        
        reader = OperationalDataReader(regular_user)
        result = reader.read_teams()
        data = json.loads(result)
        
        assert len(data["teams"]) == 1
        assert data["teams"][0]["litellm_team_id"] == "team-1"

    def test_read_keys_all_projects(self, db, admin_user, projects):
        """Should read keys from all accessible projects."""
        key1 = Key.objects.create(
            project=projects[0],
            name="Key 1",
            litellm_secret="secret-1",
            litellm_alias="alias-1",
            litellm_token="token-1",
            masked_key="***masked-1",
            created_by=admin_user,
        )
        key2 = Key.objects.create(
            project=projects[1],
            name="Key 2",
            litellm_secret="secret-2",
            litellm_alias="alias-2",
            litellm_token="token-2",
            masked_key="***masked-2",
            created_by=admin_user,
        )
        
        reader = OperationalDataReader(admin_user)
        result = reader.read_keys()
        data = json.loads(result)
        
        assert len(data["keys"]) == 2
        key_names = {k["name"] for k in data["keys"]}
        assert "Key 1" in key_names
        assert "Key 2" in key_names

    def test_read_keys_filter_by_project(self, db, admin_user, projects):
        """Should filter keys by project when specified."""
        key1 = Key.objects.create(
            project=projects[0],
            name="Key 1",
            litellm_secret="secret-1",
            litellm_alias="alias-1",
            litellm_token="token-1",
            masked_key="***masked-1",
            created_by=admin_user,
        )
        key2 = Key.objects.create(
            project=projects[1],
            name="Key 2",
            litellm_secret="secret-2",
            litellm_alias="alias-2",
            litellm_token="token-2",
            masked_key="***masked-2",
            created_by=admin_user,
        )
        
        reader = OperationalDataReader(admin_user)
        result = reader.read_keys(project_id=str(projects[0].uuid))
        data = json.loads(result)
        
        assert len(data["keys"]) == 1
        assert data["keys"][0]["name"] == "Key 1"

    def test_read_keys_no_sensitive_data(self, db, admin_user, projects):
        """Key data should not include sensitive secrets."""
        key = Key.objects.create(
            project=projects[0],
            name="Key 1",
            litellm_secret="super-secret-value",
            litellm_alias="alias-1",
            litellm_token="token-1",
            masked_key="***masked-1",
            created_by=admin_user,
        )
        
        reader = OperationalDataReader(admin_user)
        result = reader.read_keys()
        data = json.loads(result)
        
        key_data = data["keys"][0]
        assert "litellm_secret" not in key_data
        assert "litellm_token" not in key_data
        assert key_data["masked_key"] == "***masked-1"

    def test_read_keys_member_denied_for_other_projects(
        self, db, regular_user, projects
    ):
        """Members should be denied access to keys in projects they don't have access to."""
        ProjectUserPermissions.objects.create(
            project=projects[0],
            user=regular_user,
            role="member",
        )
        
        key = Key.objects.create(
            project=projects[1],
            name="Key 2",
            litellm_secret="secret-2",
            litellm_alias="alias-2",
            litellm_token="token-2",
            masked_key="***masked-2",
            created_by=regular_user,
        )
        
        reader = OperationalDataReader(regular_user)
        # Try to read keys from project they don't have access to
        with pytest.raises(Exception):  # Should raise MCPAuthorizationError
            reader.read_keys(project_id=str(projects[1].uuid))
