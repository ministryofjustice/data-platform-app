"""Tests for MCP authorization module."""

import uuid

import pytest

from data_platform_mcp.auth import MCPAuthorization, MCPAuthorizationError
from projects.models import BusinessUnit, Project, ProjectUserPermissions


@pytest.mark.django_db
class TestMCPAuthorization:
    """Test cases for MCPAuthorization class."""

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
    def project(self, db, admin_user, business_unit):
        """Create a test project."""
        return Project.objects.create(
            name="Test Project",
            description="A test project",
            business_unit=business_unit,
            created_by=admin_user,
        )

    def test_authorize_project_access_superuser(self, admin_user, project):
        """Superuser should have access to all projects."""
        auth = MCPAuthorization(admin_user)
        authorized_project = auth.authorize_project_access(str(project.uuid))
        assert authorized_project.id == project.id

    def test_authorize_project_access_member_without_permission(self, regular_user, project):
        """User without permission should be denied access."""
        auth = MCPAuthorization(regular_user)
        with pytest.raises(MCPAuthorizationError):
            auth.authorize_project_access(str(project.uuid))

    def test_authorize_project_access_member_with_permission(self, db, regular_user, project):
        """User with permission should have access."""
        ProjectUserPermissions.objects.create(
            project=project,
            user=regular_user,
            role="member",
        )
        auth = MCPAuthorization(regular_user)
        authorized_project = auth.authorize_project_access(str(project.uuid))
        assert authorized_project.id == project.id

    def test_authorize_project_access_nonexistent_project(self, regular_user):
        """Access to non-existent project should be denied."""
        auth = MCPAuthorization(regular_user)
        fake_uuid = str(uuid.uuid4())
        with pytest.raises(MCPAuthorizationError):
            auth.authorize_project_access(fake_uuid)

    def test_authorize_project_access_admin_role_required(self, db, regular_user, project):
        """Requiring admin role should check user's role."""
        # Member role
        ProjectUserPermissions.objects.create(
            project=project,
            user=regular_user,
            role="member",
        )
        auth = MCPAuthorization(regular_user)
        with pytest.raises(MCPAuthorizationError):
            auth.authorize_project_access(
                str(project.uuid),
                required_role="admin",
            )

    def test_authorize_project_access_admin_role_granted(self, db, regular_user, project):
        """Admin role should allow admin operations."""
        ProjectUserPermissions.objects.create(
            project=project,
            user=regular_user,
            role="admin",
        )
        auth = MCPAuthorization(regular_user)
        authorized_project = auth.authorize_project_access(
            str(project.uuid),
            required_role="admin",
        )
        assert authorized_project.id == project.id

    def test_authorize_admin_access_superuser(self, admin_user):
        """Superuser should pass admin authorization."""
        auth = MCPAuthorization(admin_user)
        auth.authorize_admin_access()  # Should not raise

    def test_authorize_admin_access_regular_user(self, regular_user):
        """Regular user should fail admin authorization."""
        auth = MCPAuthorization(regular_user)
        with pytest.raises(MCPAuthorizationError):
            auth.authorize_admin_access()

    def test_authorize_key_creation(self, db, regular_user, project):
        """Only admins should be able to create keys."""
        ProjectUserPermissions.objects.create(
            project=project,
            user=regular_user,
            role="admin",
        )
        auth = MCPAuthorization(regular_user)
        authorized_project = auth.authorize_key_creation(str(project.uuid))
        assert authorized_project.id == project.id

    def test_authorize_key_creation_member_denied(self, db, regular_user, project):
        """Members should not be able to create keys."""
        ProjectUserPermissions.objects.create(
            project=project,
            user=regular_user,
            role="member",
        )
        auth = MCPAuthorization(regular_user)
        with pytest.raises(MCPAuthorizationError):
            auth.authorize_key_creation(str(project.uuid))

    def test_get_accessible_projects_superuser(self, db, admin_user, project, business_unit):
        """Superuser should see all projects."""
        other_project = Project.objects.create(
            name="Other Project",
            description="Another project",
            business_unit=business_unit,
            created_by=admin_user,
        )
        auth = MCPAuthorization(admin_user)
        projects = auth.get_accessible_projects()
        assert len(projects) == 2
        assert project in projects
        assert other_project in projects

    def test_get_accessible_projects_member(
        self, db, regular_user, project, business_unit, admin_user
    ):
        """Member should only see projects they have access to."""
        other_project = Project.objects.create(
            name="Other Project",
            description="Another project",
            business_unit=business_unit,
            created_by=admin_user,
        )
        ProjectUserPermissions.objects.create(
            project=project,
            user=regular_user,
            role="member",
        )
        auth = MCPAuthorization(regular_user)
        projects = auth.get_accessible_projects()
        assert len(projects) == 1
        assert project in projects
        assert other_project not in projects

    def test_get_accessible_projects_no_access(self, regular_user):
        """User with no projects should see empty list."""
        auth = MCPAuthorization(regular_user)
        projects = auth.get_accessible_projects()
        assert len(projects) == 0


@pytest.mark.django_db
class TestMCPAuthorizationErrorHandling:
    """Test error handling in MCP authorization."""

    def test_authorization_error_is_exception(self):
        """MCPAuthorizationError should be an Exception."""
        error = MCPAuthorizationError("test error")
        assert isinstance(error, Exception)
        assert str(error) == "test error"
