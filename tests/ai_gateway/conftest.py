import pytest
from model_bakery import baker


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
        litellm_secret="sk-full-secret",
        masked_key="sk-abc...secret",
        created_by=user,
    )
