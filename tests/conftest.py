import pytest
from model_bakery import baker


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
