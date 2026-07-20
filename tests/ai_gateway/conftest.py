import pytest
from model_bakery import baker


@pytest.fixture
def key(db, project, user):
    """An existing AI Gateway key belonging to ``project``."""
    return baker.make(
        "ai_gateway.Key",
        project=project,
        name="primary-key",
        litellm_secret="sk-full-secret",
        masked_key="sk-abc...secret",
        created_by=user,
    )
