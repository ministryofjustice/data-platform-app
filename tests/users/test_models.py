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
        user = User.objects.create_user(
            username="jane.doe",
            email="jane@example.com",
            password="unsafe-test-password",
        )

        assert user.username == "jane.doe"
        assert user.email == "jane@example.com"
        assert user.pk is not None
