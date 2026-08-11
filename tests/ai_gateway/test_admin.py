from unittest.mock import create_autospec, patch

import pytest
from django.urls import reverse
from model_bakery import baker

from ai_gateway.exceptions import AIGatewayAPIError
from ai_gateway.services import AccessGroupService


@pytest.fixture
def superuser(db):
    """A superuser able to access the Django admin."""
    return baker.make("users.User", is_staff=True, is_superuser=True)


@pytest.fixture
def team(db, project):
    """An AI Gateway team belonging to ``project``."""
    return baker.make("ai_gateway.Team", project=project, litellm_team_id="team-abc-123")


@pytest.fixture
def access_group_service():
    """Patch AccessGroupService.from_settings with an autospecced context-manager instance."""
    service = create_autospec(AccessGroupService, instance=True)
    service.__enter__.return_value = service
    service.__exit__.return_value = False
    service.list_access_groups.return_value = [
        {"access_group_id": "ag-1", "access_group_name": "generally-available-models"},
        {"access_group_id": "ag-2", "access_group_name": "restricted-models"},
    ]
    service.get_team_access_group_ids.return_value = ["ag-1"]

    with patch("ai_gateway.services.AccessGroupService.from_settings", return_value=service):
        yield service


class TestAIGatewayTeamAdminChangeView:
    def test_renders_access_groups_with_current_selection(
        self, client, superuser, team, access_group_service
    ):
        client.force_login(superuser)
        url = reverse("admin:ai_gateway_team_change", args=[team.pk])

        response = client.get(url)

        assert response.status_code == 200
        form = response.context["adminform"].form
        assert form.fields["access_groups"].choices == [
            ("ag-1", "generally-available-models"),
            ("ag-2", "restricted-models"),
        ]
        assert form.initial["access_groups"] == ["ag-1"]

    def test_rendering_fetches_from_gateway_once(
        self, client, superuser, team, access_group_service
    ):
        client.force_login(superuser)
        url = reverse("admin:ai_gateway_team_change", args=[team.pk])

        client.get(url)

        assert access_group_service.list_access_groups.call_count == 1
        assert access_group_service.get_team_access_group_ids.call_count == 1

    def test_viewing_logs_current_access_groups(
        self, client, superuser, team, access_group_service, caplog
    ):
        client.force_login(superuser)
        url = reverse("admin:ai_gateway_team_change", args=[team.pk])

        with caplog.at_level("INFO", logger="ai_gateway.admin"):
            client.get(url)

        assert any(
            "access groups for team team-abc-123 viewed" in record.getMessage()
            and "['ag-1']" in record.getMessage()
            for record in caplog.records
        )

    def test_saving_updates_team_access_groups(
        self, client, superuser, team, access_group_service
    ):
        client.force_login(superuser)
        url = reverse("admin:ai_gateway_team_change", args=[team.pk])

        response = client.post(url, {"access_groups": ["ag-2"], "_save": ""})

        assert response.status_code == 302
        access_group_service.set_team_access_groups.assert_called_once_with(team, ["ag-2"])

    def test_saving_logs_new_access_groups(
        self, client, superuser, team, access_group_service, caplog
    ):
        client.force_login(superuser)
        url = reverse("admin:ai_gateway_team_change", args=[team.pk])

        with caplog.at_level("INFO", logger="ai_gateway.admin"):
            client.post(url, {"access_groups": ["ag-2"], "_save": ""})

        assert any(
            "access groups for team team-abc-123 updated" in record.getMessage()
            and "['ag-2']" in record.getMessage()
            for record in caplog.records
        )

    def test_load_error_is_reported_not_raised(
        self, client, superuser, team, access_group_service
    ):
        access_group_service.list_access_groups.side_effect = AIGatewayAPIError(
            503, "gateway down"
        )
        client.force_login(superuser)
        url = reverse("admin:ai_gateway_team_change", args=[team.pk])

        response = client.get(url)

        assert response.status_code == 200
        messages = [str(message) for message in response.context["messages"]]
        assert any("Could not load access groups" in message for message in messages)

    def test_save_error_is_reported_not_raised(
        self, client, superuser, team, access_group_service
    ):
        access_group_service.set_team_access_groups.side_effect = AIGatewayAPIError(
            503, "gateway down"
        )
        client.force_login(superuser)
        url = reverse("admin:ai_gateway_team_change", args=[team.pk])

        response = client.post(url, {"access_groups": ["ag-2"], "_save": ""}, follow=True)

        assert response.status_code == 200
        messages = [str(message) for message in response.context["messages"]]
        assert any("Could not update access groups" in message for message in messages)
