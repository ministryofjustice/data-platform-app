import pytest
from model_bakery import baker

from ai_gateway.models import Key, Team


@pytest.fixture
def project(db, user):
    return baker.make("projects.Project", name="Example Project", slug="example-slug")


class TestTeam:
    def test_str(self, project):
        team = Team.objects.create(project=project, litellm_team_id="team-1")

        assert str(team) == "AI Gateway team for Example Project"


class TestKey:
    def test_str_is_the_alias(self, project):
        key = Key.objects.create(
            project=project,
            name="Example",
            litellm_token="tok-1",
            masked_key="sk-abc...wxyz",
        )

        assert str(key) == "Example"
