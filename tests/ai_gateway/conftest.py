import pytest
from model_bakery import baker


# TODO consider if this can be removed once project creation branch added in
@pytest.fixture
def project(db, user):
    """A project with the test user as an admin member."""
    project = baker.make(
        "projects.Project", name="Example Project", slug="example-slug", created_by=user
    )
    baker.make("projects.ProjectUserPermissions", project=project, user=user, role="admin")
    return project


@pytest.fixture
def non_member(db):
    """A user who is not a member of ``project``."""
    return baker.make("users.User", email="outsider@example.com")


@pytest.fixture
def key(db, project, user):
    """An existing AI gateway key belonging to ``project``."""
    return baker.make(
        "ai_gateway.Key",
        project=project,
        name="primary-key",
        litellm_secret="sk-abcdefghijklmnopqrstuvwxyz",
        masked_key="sk-abc...wxyz",
        created_by=user,
    )
