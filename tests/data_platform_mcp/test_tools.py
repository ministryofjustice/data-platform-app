"""Tests for API key lifecycle management tools."""

import uuid

import pytest

from ai_gateway.models import Key
from data_platform_mcp.auth import MCPAuthorizationError
from data_platform_mcp.tools import APIKeyManager, APIKeyOperationError
from projects.models import BusinessUnit, Project, ProjectUserPermissions


@pytest.mark.django_db
class TestAPIKeyManager:
    """Tests for APIKeyManager."""

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
    def member_user(self, db):
        """Create a member user."""
        from django.contrib.auth import get_user_model

        User = get_user_model()
        return User.objects.create_user(
            oid=uuid.uuid4(),
            email="member@example.com",
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

    def test_create_key_by_admin(self, admin_user, project):
        """Admins should be able to create keys."""
        manager = APIKeyManager(admin_user)
        result = manager.create_key(
            project_id=str(project.uuid),
            name="My Key",
            models=["gpt-4", "claude-3"],
        )

        assert result["name"] == "My Key"
        assert result["models"] == ["gpt-4", "claude-3"]
        assert "masked_key" in result
        assert "created" in result

    def test_create_key_by_project_admin(self, db, member_user, project):
        """Project admins should be able to create keys."""
        ProjectUserPermissions.objects.create(
            project=project,
            user=member_user,
            role="admin",
        )

        manager = APIKeyManager(member_user)
        result = manager.create_key(
            project_id=str(project.uuid),
            name="Admin Key",
            models=["gpt-4"],
        )

        assert result["name"] == "Admin Key"
        # Verify key exists in database
        assert Key.objects.filter(
            project=project,
            name="Admin Key",
        ).exists()

    def test_create_key_denied_for_member(self, db, member_user, project):
        """Members should NOT be able to create keys."""
        ProjectUserPermissions.objects.create(
            project=project,
            user=member_user,
            role="member",
        )

        manager = APIKeyManager(member_user)
        with pytest.raises(MCPAuthorizationError):
            manager.create_key(
                project_id=str(project.uuid),
                name="Unauthorized Key",
                models=["gpt-4"],
            )

    def test_create_key_validation_empty_name(self, admin_user, project):
        """Creating key with empty name should fail."""
        manager = APIKeyManager(admin_user)
        with pytest.raises(APIKeyOperationError):
            manager.create_key(
                project_id=str(project.uuid),
                name="",
                models=["gpt-4"],
            )

    def test_create_key_validation_no_models(self, admin_user, project):
        """Creating key with no models should fail."""
        manager = APIKeyManager(admin_user)
        with pytest.raises(APIKeyOperationError):
            manager.create_key(
                project_id=str(project.uuid),
                name="My Key",
                models=[],
            )

    def test_create_key_validation_duplicate_name(self, db, admin_user, project):
        """Creating key with duplicate name should fail."""
        # Create first key
        manager = APIKeyManager(admin_user)
        manager.create_key(
            project_id=str(project.uuid),
            name="My Key",
            models=["gpt-4"],
        )

        # Try to create second with same name
        with pytest.raises(APIKeyOperationError):
            manager.create_key(
                project_id=str(project.uuid),
                name="My Key",
                models=["claude-3"],
            )

    def test_create_key_max_per_project(self, db, admin_user, project):
        """Should enforce maximum keys per project."""
        manager = APIKeyManager(admin_user)

        # Create max keys
        for i in range(APIKeyManager.MAX_KEYS_PER_PROJECT):
            manager.create_key(
                project_id=str(project.uuid),
                name=f"Key {i}",
                models=["gpt-4"],
            )

        # Try to create one more
        with pytest.raises(APIKeyOperationError):
            manager.create_key(
                project_id=str(project.uuid),
                name="Extra Key",
                models=["gpt-4"],
            )

    def test_delete_key_by_admin(self, db, admin_user, project):
        """Admins should be able to delete keys."""
        # Create a key first
        key = Key.objects.create(
            project=project,
            name="Key to Delete",
            litellm_secret="secret",
            litellm_alias="alias",
            litellm_token="token",
            masked_key="***masked",
            created_by=admin_user,
        )

        manager = APIKeyManager(admin_user)
        manager.delete_key(str(key.id), str(project.uuid))

        # Verify deleted
        assert not Key.objects.filter(id=key.id).exists()

    def test_delete_key_denied_for_member(self, db, member_user, project):
        """Members should NOT be able to delete keys."""
        ProjectUserPermissions.objects.create(
            project=project,
            user=member_user,
            role="member",
        )

        # Create a key
        key = Key.objects.create(
            project=project,
            name="Key",
            litellm_secret="secret",
            litellm_alias="alias",
            litellm_token="token",
            masked_key="***masked",
            created_by=member_user,
        )

        manager = APIKeyManager(member_user)
        with pytest.raises(MCPAuthorizationError):
            manager.delete_key(str(key.id), str(project.uuid))

    def test_rotate_key_by_admin(self, db, admin_user, project):
        """Admins should be able to rotate keys."""
        # Create a key first
        key = Key.objects.create(
            project=project,
            name="Key to Rotate",
            litellm_secret="old_secret",
            litellm_alias="alias",
            litellm_token="old_token",
            masked_key="***masked",
            created_by=admin_user,
            models=["gpt-4"],
        )

        manager = APIKeyManager(admin_user)
        result = manager.rotate_key(str(key.id), str(project.uuid))

        assert result["id"] == str(key.id)
        assert "rotated" in result

    def test_rotate_key_denied_for_member(self, db, member_user, project):
        """Members should NOT be able to rotate keys."""
        ProjectUserPermissions.objects.create(
            project=project,
            user=member_user,
            role="member",
        )

        # Create a key
        key = Key.objects.create(
            project=project,
            name="Key",
            litellm_secret="secret",
            litellm_alias="alias",
            litellm_token="token",
            masked_key="***masked",
            created_by=member_user,
        )

        manager = APIKeyManager(member_user)
        with pytest.raises(MCPAuthorizationError):
            manager.rotate_key(str(key.id), str(project.uuid))

    def test_list_keys_member_sees_own(self, db, member_user, project):
        """Members should see keys in their projects."""
        ProjectUserPermissions.objects.create(
            project=project,
            user=member_user,
            role="member",
        )

        # Create keys
        Key.objects.create(
            project=project,
            name="Key 1",
            litellm_secret="secret1",
            litellm_alias="alias1",
            litellm_token="token1",
            masked_key="***1",
            created_by=member_user,
        )
        Key.objects.create(
            project=project,
            name="Key 2",
            litellm_secret="secret2",
            litellm_alias="alias2",
            litellm_token="token2",
            masked_key="***2",
            created_by=member_user,
        )

        manager = APIKeyManager(member_user)
        keys = manager.list_keys(str(project.uuid))

        assert len(keys) == 2
        key_names = {k["name"] for k in keys}
        assert "Key 1" in key_names
        assert "Key 2" in key_names

    def test_list_keys_no_sensitive_data(self, db, admin_user, project):
        """Listed keys should not include sensitive data."""
        Key.objects.create(
            project=project,
            name="Key",
            litellm_secret="super_secret",
            litellm_alias="alias",
            litellm_token="super_token",
            masked_key="***masked",
            created_by=admin_user,
        )

        manager = APIKeyManager(admin_user)
        keys = manager.list_keys(str(project.uuid))

        assert len(keys) == 1
        assert "litellm_secret" not in keys[0]
        assert "litellm_token" not in keys[0]
        assert keys[0]["masked_key"] == "***masked"

    def test_list_keys_denied_for_unauthorized_user(self, db, regular_user, project):
        """Users without project access should be denied."""
        manager = APIKeyManager(regular_user)
        with pytest.raises(MCPAuthorizationError):
            manager.list_keys(str(project.uuid))
