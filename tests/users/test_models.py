import pytest
from django.conf import settings
from django.contrib.auth import get_user_model

from users.models import User


@pytest.mark.django_db
class TestUserModel:
    """Tests for project-specific User model wiring."""

    def test_auth_user_model_setting_points_to_custom_user(self):
        assert settings.AUTH_USER_MODEL == "users.User"

    def test_get_user_model_returns_project_user_class(self):
        active_user_model = get_user_model()

        assert active_user_model is User

    def test_can_create_user_with_manager(self):
        oid = "4a1b2c3d-1234-5678-9abc-def012345678"
        user = User.objects.create_user(
            oid=oid,
            username="Jane Doe",
            email="jane@example.com",
            password="unsafe-test-password",
        )

        assert str(user.oid) == oid
        assert user.username == "Jane Doe"
        assert user.email == "jane@example.com"
        assert user.pk is not None
        assert user.check_password("unsafe-test-password") is True

    def test_create_user_lowercases_email(self):
        user = User.objects.create_user(
            oid="4a1b2c3d-1234-5678-9abc-def012345678",
            email="Jane.Doe@Example.COM",
        )

        assert user.email == "jane.doe@example.com"

    def test_save_lowercases_email(self):
        user = User(
            oid="4a1b2c3d-1234-5678-9abc-def012345678",
            email="Jane.Doe@Example.COM",
        )

        user.save()

        assert user.email == "jane.doe@example.com"

    def test_create_superuser_sets_staff_and_superuser_flags(self):
        user = User.objects.create_superuser(
            oid="4a1b2c3d-1234-5678-9abc-def012345678",
            password="unsafe-test-password",
        )

        assert user.is_staff is True
        assert user.is_superuser is True

    def test_create_superuser_rejects_non_staff(self):
        with pytest.raises(ValueError):
            User.objects.create_superuser(
                oid="4a1b2c3d-1234-5678-9abc-def012345678", is_staff=False
            )

    def test_create_superuser_rejects_non_superuser(self):
        with pytest.raises(ValueError):
            User.objects.create_superuser(
                oid="4a1b2c3d-1234-5678-9abc-def012345678", is_superuser=False
            )

    def test_create_user_without_oid_is_rejected(self):
        with pytest.raises(ValueError):
            User.objects.create_user(oid=None, email="no-oid@example.com")

    def test_str_prefers_username_then_email_then_oid(self):
        oid = "4a1b2c3d-1234-5678-9abc-def012345678"

        assert str(User(oid=oid, username="Jane Doe", email="jane@example.com")) == ("Jane Doe")
        assert str(User(oid=oid, email="jane@example.com")) == "jane@example.com"
        assert str(User(oid=oid)) == oid
