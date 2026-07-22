from unittest.mock import create_autospec, patch

import pytest
from model_bakery import baker

from ai_gateway.services import KeyService


@pytest.fixture
def anonymous_user():
    """An unsaved AnonymousUser instance."""
    from django.contrib.auth.models import AnonymousUser

    return AnonymousUser()


@pytest.fixture
def user(db):
    """A saved User instance with no special permissions."""

    return baker.make("users.User")


@pytest.fixture
def project(db, user):
    """A project with the test user as an admin member."""
    project = baker.make("projects.Project", name="Example Project", created_by=user)
    baker.make("projects.ProjectUserPermissions", project=project, user=user, role="admin")
    return project


@pytest.fixture
def non_project_user(db):
    """A user who is not part of any project."""

    non_project_user = baker.make("users.User", email="non_project_user@example.com")

    return non_project_user


@pytest.fixture
def key_service():
    """Patch KeyService.from_settings with an autospecced instance used as a context manager."""
    service = create_autospec(KeyService, instance=True)
    service.__enter__.return_value = service
    service.__exit__.return_value = False
    service.list_default_models.return_value = [
        {
            "model_name": "gpt-4",
            "litellm_params": {
                "ai_model_name": "GPT-4",
                "ai_model_family": "GPT",
                "ai_model_provider": "OpenAI",
                "ai_model_generally_available": True,
            },
            "input_cost_per_million": 30.0,
            "output_cost_per_million": 60.0,
        },
        {
            "model_name": "claude-3",
            "litellm_params": {
                "ai_model_name": "Claude 3",
                "ai_model_family": "Claude",
                "ai_model_provider": "Anthropic",
                "ai_model_generally_available": True,
            },
            "input_cost_per_million": 15.0,
            "output_cost_per_million": 75.0,
        },
    ]
    service.get_models_for_key.return_value = ["gpt-4"]

    with patch("ai_gateway.services.KeyService.from_settings", return_value=service):
        yield service
