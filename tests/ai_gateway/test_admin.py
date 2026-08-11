from unittest.mock import create_autospec, patch

import pytest
from django.urls import reverse
from model_bakery import baker

from ai_gateway.exceptions import AIGatewayAPIError
from ai_gateway.services import AccessGroupService, KeyService


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


@pytest.fixture(autouse=True)
def patched_key_service():
    """Patch KeyService.from_settings with an autospecced context-manager instance."""
    service = create_autospec(KeyService, instance=True)
    service.__enter__.return_value = service
    service.__exit__.return_value = False
    service.prune_team_keys_to_allowed_models.return_value = ([], [])

    with patch("ai_gateway.services.KeyService.from_settings", return_value=service):
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
        options = {
            str(widget.data["value"]): widget.data["attrs"]
            for widget in form["access_groups"].subwidgets
        }
        assert options["ag-1"].get("disabled") is True
        assert "disabled" not in options["ag-2"]

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
        access_group_service.set_team_access_groups.assert_called_once_with(team, ["ag-2", "ag-1"])

    def test_saving_logs_new_access_groups(
        self, client, superuser, team, access_group_service, caplog
    ):
        client.force_login(superuser)
        url = reverse("admin:ai_gateway_team_change", args=[team.pk])

        with caplog.at_level("INFO", logger="ai_gateway.admin"):
            client.post(url, {"access_groups": ["ag-2"], "_save": ""})

        assert any(
            "access groups for team team-abc-123 updated" in record.getMessage()
            and "'ag-2'" in record.getMessage()
            for record in caplog.records
        )

    def test_load_error_propagates(self, client, superuser, team, access_group_service):
        access_group_service.list_access_groups.side_effect = AIGatewayAPIError(
            503, "gateway down"
        )
        client.force_login(superuser)
        url = reverse("admin:ai_gateway_team_change", args=[team.pk])

        with pytest.raises(AIGatewayAPIError):
            client.get(url)

    def test_save_error_propagates(self, client, superuser, team, access_group_service):
        access_group_service.set_team_access_groups.side_effect = AIGatewayAPIError(
            503, "gateway down"
        )
        client.force_login(superuser)
        url = reverse("admin:ai_gateway_team_change", args=[team.pk])

        with pytest.raises(AIGatewayAPIError):
            client.post(url, {"access_groups": ["ag-2"], "_save": ""})

    def test_removing_access_group_prunes_team_keys(
        self, client, superuser, team, access_group_service, patched_key_service
    ):
        access_group_service.get_team_access_group_ids.return_value = ["ag-1", "ag-2"]
        patched_key_service.prune_team_keys_to_allowed_models.return_value = (["alias-1"], [])
        client.force_login(superuser)
        url = reverse("admin:ai_gateway_team_change", args=[team.pk])

        response = client.post(url, {"_save": ""}, follow=True)

        assert response.status_code == 200
        patched_key_service.prune_team_keys_to_allowed_models.assert_called_once_with(team)
        messages = [str(message) for message in response.context["messages"]]
        assert any(
            "Removed newly restricted models from 1 key(s)." in message for message in messages
        )

    def test_adding_access_group_does_not_prune_keys(
        self, client, superuser, team, access_group_service, patched_key_service
    ):
        client.force_login(superuser)
        url = reverse("admin:ai_gateway_team_change", args=[team.pk])

        client.post(url, {"access_groups": ["ag-2"], "_save": ""})

        patched_key_service.prune_team_keys_to_allowed_models.assert_not_called()

    def test_unchanged_access_groups_skips_gateway_update(
        self, client, superuser, team, access_group_service, patched_key_service
    ):
        access_group_service.get_team_access_group_ids.return_value = ["ag-1", "ag-2"]
        client.force_login(superuser)
        url = reverse("admin:ai_gateway_team_change", args=[team.pk])

        client.post(url, {"access_groups": ["ag-2"], "_save": ""})

        access_group_service.set_team_access_groups.assert_not_called()
        patched_key_service.prune_team_keys_to_allowed_models.assert_not_called()

    def test_key_pruning_error_propagates(
        self, client, superuser, team, access_group_service, patched_key_service
    ):
        access_group_service.get_team_access_group_ids.return_value = ["ag-1", "ag-2"]
        patched_key_service.prune_team_keys_to_allowed_models.side_effect = AIGatewayAPIError(
            503, "gateway down"
        )
        client.force_login(superuser)
        url = reverse("admin:ai_gateway_team_change", args=[team.pk])

        with pytest.raises(AIGatewayAPIError):
            client.post(url, {"_save": ""})

    def test_failed_keys_are_reported(
        self, client, superuser, team, access_group_service, patched_key_service
    ):
        access_group_service.get_team_access_group_ids.return_value = ["ag-1", "ag-2"]
        patched_key_service.prune_team_keys_to_allowed_models.return_value = ([], ["alias-1"])
        client.force_login(superuser)
        url = reverse("admin:ai_gateway_team_change", args=[team.pk])

        response = client.post(url, {"_save": ""}, follow=True)

        assert response.status_code == 200
        messages = [str(message) for message in response.context["messages"]]
        assert any("Could not update 1 key(s): alias-1." in message for message in messages)
