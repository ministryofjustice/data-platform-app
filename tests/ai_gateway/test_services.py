from datetime import date, timedelta
from unittest.mock import create_autospec, patch

import pytest
from django.core.cache import cache
from django.urls import reverse

from ai_gateway.client import AIGatewayClient
from ai_gateway.exceptions import AIGatewayAPIError
from ai_gateway.models import Key, Team
from ai_gateway.services import KeyService

PLAINTEXT_KEY = "sk-plaintext-key-value-123456"


@pytest.fixture
def gateway_client():
    """An autospecced AIGatewayClient with default successful responses."""
    client = create_autospec(AIGatewayClient, instance=True)
    client.create_team.return_value = "team-xyz"
    client.generate_key.return_value = {"key": PLAINTEXT_KEY, "token": "tok-1"}
    client.regenerate_key.return_value = {
        "key": "sk-regenerated-key-value-9999",
        "token_id": "tok-2",
    }
    client.get_access_group_id.return_value = "ag-default"
    return client


@pytest.fixture(autouse=True)
def clear_django_cache():
    cache.clear()
    yield
    cache.clear()


class TestMaskKey:
    def test_masks_a_long_key(self):
        assert KeyService._mask_key("sk-very-long-secret-1234") == "...1234"

    def test_short_key_is_fully_masked(self):
        assert KeyService._mask_key("1234") == "..."


class TestBuildAlias:
    def test_prefixes_project_uuid_and_slugifies_name(self, project):
        alias = KeyService._build_alias(project, "My Special Key")

        assert alias.startswith(f"{project.uuid}-my-special-key-")

    def test_aliases_are_unique_for_the_same_inputs(self, project):
        first = KeyService._build_alias(project, "same-name")
        second = KeyService._build_alias(project, "same-name")

        assert first != second


class TestKeyServiceListModels:
    def test_returns_default_group_models_with_costs(self, project, gateway_client):
        gateway_client.list_models_for_access_group.return_value = ["gpt-4"]
        gateway_client.list_models_v1_info.return_value = [
            {
                "model_name": "gpt-4",
                "litellm_params": {},
                "model_info": {
                    "input_cost_per_token": 0.00003,
                    "output_cost_per_token": 0.00006,
                },
            },
            {
                "model_name": "internal-only",
                "litellm_params": {},
                "model_info": {},
            },
        ]

        with KeyService(gateway_client) as service:
            models = service.list_available_models(project)

        assert [model["model_name"] for model in models] == ["gpt-4"]
        assert models[0]["input_cost_per_million"] == pytest.approx(30.0)
        assert models[0]["output_cost_per_million"] == pytest.approx(60.0)

    def test_enriches_models_with_display_fields(self, project, gateway_client):
        gateway_client.list_models_for_access_group.return_value = ["gpt-4", "bare-model"]
        gateway_client.list_models_v1_info.return_value = [
            {
                "model_name": "gpt-4",
                "litellm_params": {
                    "ai_model_name": "GPT-4",
                    "ai_model_family": "GPT",
                    "ai_model_provider": "OpenAI",
                },
                "model_info": {},
            },
            {
                "model_name": "bare-model",
                "litellm_params": {},
                "model_info": {},
            },
        ]

        with KeyService(gateway_client) as service:
            models = service.list_available_models(project)

        assert models[0]["display_name"] == "GPT-4"
        assert models[0]["family"] == "GPT"
        assert models[0]["provider"] == "OpenAI"
        assert models[1]["display_name"] == "bare-model"

    def test_costs_are_none_when_pricing_is_missing(self, project, gateway_client):
        gateway_client.list_models_for_access_group.return_value = ["gpt-4"]
        gateway_client.list_models_v1_info.return_value = [
            {
                "model_name": "gpt-4",
                "litellm_params": {},
                "model_info": {},
            },
        ]

        with KeyService(gateway_client) as service:
            models = service.list_available_models(project)

        assert models[0]["input_cost_per_million"] is None
        assert models[0]["output_cost_per_million"] is None

    def test_includes_access_group_models_for_a_team(self, project, gateway_client):
        Team.objects.create(project=project, litellm_team_id="team-xyz")
        gateway_client.team_info.return_value = {
            "team_info": {"access_group_models": ["gpt-4", "restricted-model"]}
        }
        gateway_client.list_models_v1_info.return_value = [
            {
                "model_name": "gpt-4",
                "litellm_params": {},
                "model_info": {},
            },
            {
                "model_name": "restricted-model",
                "litellm_params": {},
                "model_info": {},
            },
            {
                "model_name": "other-internal",
                "litellm_params": {},
                "model_info": {},
            },
        ]

        with KeyService(gateway_client) as service:
            models = service.list_available_models(project)

        assert [model["model_name"] for model in models] == ["gpt-4", "restricted-model"]
        gateway_client.team_info.assert_called_once_with("team-xyz")
        gateway_client.list_models_for_access_group.assert_not_called()


class TestKeyServiceCreateKey:
    def test_creates_team_lazily_and_persists_metadata(
        self, project, user, gateway_client, settings
    ):
        settings.DEFAULT_ACCESS_GROUP_NAME = "generally-available-models"
        gateway_client.get_access_group_id.return_value = "ag-default"

        with KeyService(gateway_client) as service:
            plaintext = service.create_key(project, "primary-key", ["gpt-4"], user)

        assert plaintext == PLAINTEXT_KEY
        gateway_client.get_access_group_id.assert_called_once_with("generally-available-models")
        gateway_client.create_team.assert_called_once_with(str(project.uuid), ["ag-default"])
        team = Team.objects.get(project=project)
        assert team.litellm_team_id == "team-xyz"

        gateway_client.generate_key.assert_called_once()
        assert gateway_client.generate_key.call_args.args == ("team-xyz",)
        assert gateway_client.generate_key.call_args.kwargs["models"] == ["gpt-4"]
        alias_sent = gateway_client.generate_key.call_args.kwargs["key_alias"]
        assert alias_sent.startswith(f"{project.uuid}-primary-key-")

        key = Key.objects.get(project=project)
        assert key.name == "primary-key"
        assert key.litellm_alias == alias_sent
        assert key.litellm_secret == PLAINTEXT_KEY
        assert key.litellm_token == "tok-1"
        assert key.masked_key != PLAINTEXT_KEY
        assert PLAINTEXT_KEY not in key.masked_key
        assert key.models == ["gpt-4"]
        assert key.created_by == user
        gateway_client.close.assert_called_once()

    def test_reuses_existing_team(self, project, user, gateway_client):
        Team.objects.create(project=project, litellm_team_id="existing-team")

        with KeyService(gateway_client) as service:
            service.create_key(project, "primary-key", ["gpt-4"], user)

        gateway_client.create_team.assert_not_called()
        gateway_client.generate_key.assert_called_once()
        assert gateway_client.generate_key.call_args.args == ("existing-team",)
        assert gateway_client.generate_key.call_args.kwargs["key_alias"].startswith(
            f"{project.uuid}-primary-key-"
        )

    def test_slugifies_name_for_gateway_alias(self, project, user, gateway_client):
        with KeyService(gateway_client) as service:
            service.create_key(project, "My Special Key", ["gpt-4"], user)

        alias_sent = gateway_client.generate_key.call_args.kwargs["key_alias"]
        assert alias_sent.startswith(f"{project.uuid}-my-special-key-")

        key = Key.objects.get(project=project)
        assert key.name == "My Special Key"
        assert key.litellm_alias == alias_sent

    def test_gateway_error_propagates_and_stores_no_key(self, project, user, gateway_client):
        gateway_client.generate_key.side_effect = AIGatewayAPIError(500, "boom")

        with pytest.raises(AIGatewayAPIError), KeyService(gateway_client) as service:
            service.create_key(project, "primary-key", ["gpt-4"], user)

        assert not Key.objects.filter(project=project).exists()
        gateway_client.close.assert_called_once()


class TestKeyServiceGetModelsForKey:
    def test_uses_cache_for_repeated_lookup(self, gateway_client, key):
        gateway_client.key_info.return_value = {"info": {"models": ["gpt-4"]}}

        with KeyService(gateway_client) as service:
            first = service.get_models_for_key(key)
            second = service.get_models_for_key(key)

        assert first == ["gpt-4"]
        assert second == ["gpt-4"]
        gateway_client.key_info.assert_called_once_with(key.litellm_secret)

    def test_cache_key_changes_when_key_modified_changes(self, gateway_client, key):
        gateway_client.key_info.side_effect = [
            {"info": {"models": ["gpt-4"]}},
            {"info": {"models": ["claude-3"]}},
        ]

        with KeyService(gateway_client) as service:
            first = service.get_models_for_key(key)

            Key.objects.filter(pk=key.pk).update(modified=key.modified + timedelta(seconds=1))
            key.refresh_from_db(fields=["modified"])

            second = service.get_models_for_key(key)

        assert first == ["gpt-4"]
        assert second == ["claude-3"]
        assert gateway_client.key_info.call_count == 2


class TestKeyServiceUpdateModelsForKey:
    def test_updates_models_and_records_history(self, gateway_client, key, user):
        key.models = ["gpt-4"]
        key.save(update_fields=["models", "modified"])
        original_modified = key.modified

        with KeyService(gateway_client) as service:
            service.update_models_for_key(
                key,
                ["claude-3"],
                changed_by=user,
            )

        gateway_client.update_key_models.assert_called_once_with(key.litellm_token, ["claude-3"])
        key.refresh_from_db(fields=["models", "modified"])
        assert key.modified > original_modified
        assert key.models == ["claude-3"]

        latest_history = key.history.latest()
        previous_history = latest_history.prev_record
        assert latest_history.models == ["claude-3"]
        assert latest_history.history_user == user
        assert latest_history.history_change_reason == "Models changed"
        assert previous_history.models == ["gpt-4"]

    def test_gateway_error_records_no_history(self, gateway_client, key, user):
        key.models = ["gpt-4"]
        key.save(update_fields=["models", "modified"])
        history_count = key.history.count()
        gateway_client.update_key_models.side_effect = AIGatewayAPIError(500, "boom")

        with pytest.raises(AIGatewayAPIError), KeyService(gateway_client) as service:
            service.update_models_for_key(
                key,
                ["claude-3"],
                changed_by=user,
            )

        key.refresh_from_db()
        assert key.models == ["gpt-4"]
        assert key.history.count() == history_count


class TestKeyServiceRegenerateKey:
    def test_regenerates_and_persists_secret_and_mask(self, project, user, gateway_client):
        key = Key.objects.create(
            project=project,
            name="primary-key",
            litellm_alias=f"{project.uuid}-primary-key-seed",
            litellm_secret="sk-old-secret",
            litellm_token="tok-1",
            masked_key="...secret",
            created_by=user,
        )

        with KeyService(gateway_client) as service:
            new_secret = service.regenerate_key(key)

        key.refresh_from_db()
        assert new_secret == "sk-regenerated-key-value-9999"
        assert key.litellm_secret == "sk-regenerated-key-value-9999"
        assert key.litellm_token == "tok-2"
        assert key.masked_key == "...9999"
        gateway_client.regenerate_key.assert_called_once_with("tok-1")

    def test_raises_when_key_row_is_missing(self, project, gateway_client):
        with KeyService(gateway_client) as service, pytest.raises(Key.DoesNotExist):
            service.regenerate_key(
                Key(
                    pk=9999,
                    project=project,
                    name="bad_key",
                    litellm_alias="alias",
                    litellm_secret="sk-1234",
                    litellm_token="bad_token",
                    masked_key="...bad_key",
                    created_by=None,
                )
            )


class TestKeyServiceDeleteKey:
    def test_deletes_gateway_key_and_object(self, gateway_client, key):
        with KeyService(gateway_client) as service:
            service.delete_key(key)

        gateway_client.delete_key.assert_called_once_with(key.litellm_token)
        assert not Key.objects.filter(pk=key.pk).exists()


class TestKeyServiceBulkDeleteKeys:
    def test_delegates_to_client(self, gateway_client):
        keys = ["sk-key-one", "sk-key-two", "sk-key-three"]

        with KeyService(gateway_client) as service:
            service.bulk_delete_keys(keys)

        gateway_client.bulk_delete_keys.assert_called_once_with(keys)

    def test_empty_list(self, gateway_client):
        with KeyService(gateway_client) as service:
            service.bulk_delete_keys([])

        gateway_client.bulk_delete_keys.assert_not_called()

    def test_gateway_error_propagates(self, gateway_client):
        gateway_client.bulk_delete_keys.side_effect = AIGatewayAPIError(500, "boom")

        with pytest.raises(AIGatewayAPIError), KeyService(gateway_client) as service:
            service.bulk_delete_keys(["sk-key-one"])


class TestKeyServiceDeleteTeam:
    def test_delegates_to_client(self, gateway_client):
        with KeyService(gateway_client) as service:
            service.delete_team("team-abc-123")

        gateway_client.delete_team.assert_called_once_with("team-abc-123")

    def test_gateway_error_propagates(self, gateway_client):
        gateway_client.delete_team.side_effect = AIGatewayAPIError(404, "team not found")

        with pytest.raises(AIGatewayAPIError), KeyService(gateway_client) as service:
            service.delete_team("team-abc-123")


class TestKeyServiceUsageData:
    def test_overview_returns_no_usage_without_gateway_team(self, project, gateway_client):
        with KeyService(gateway_client) as service:
            result = service.get_usage_overview(project, date(2026, 8, 1))

        assert result == {"has_usage": False}
        gateway_client.team_daily_activity.assert_not_called()
        gateway_client.team_info.assert_not_called()

    def test_overview_aggregates_daily_monthly_and_budget_data(self, project, gateway_client):
        Team.objects.create(project=project, litellm_team_id="team-xyz")
        gateway_client.team_daily_activity.side_effect = [
            {
                "results": [
                    {"date": "2026-08-10", "metrics": {"spend": 10.12}},
                    {"date": "2026-08-11", "metrics": {"spend": 2.22}},
                ]
            },
            {
                "results": [
                    {"date": "2026-08-10", "metrics": {"spend": 10.12}},
                    {"date": "2026-07-05", "metrics": {"spend": 5}},
                    {"date": "2026-03-01", "metrics": {"spend": 1.34}},
                ]
            },
        ]
        gateway_client.team_info.return_value = {"team_info": {"max_budget": 100}}

        with KeyService(gateway_client) as service:
            result = service.get_usage_overview(project, date(2026, 8, 20))

        assert result["has_usage"] is True
        assert result["total_spend"] == 12.34
        assert result["max_budget"] == 100
        assert result["budget_remaining"] == 87.66
        assert result["percent_used"] == 12.3
        assert result["daily_spend"] == [
            {"label": "11 August 2026", "spend": 2.22},
            {"label": "10 August 2026", "spend": 10.12},
        ]
        assert result["daily_spend_preview"] == result["daily_spend"]
        assert result["daily_show_all"] is None
        assert result["daily_chart"] is None
        assert result["daily_chart_label"] == "Daily spend for August 2026"
        assert result["monthly_spend_rows"] == [
            {"label": "August 2026", "spend": 10.12},
            {"label": "July 2026", "spend": 5},
            {"label": "March 2026", "spend": 1.34},
        ]
        assert result["monthly_chart"] is None
        assert gateway_client.team_daily_activity.call_args_list[0].args == (
            "team-xyz",
            "2026-08-01",
            "2026-08-31",
        )
        assert gateway_client.team_daily_activity.call_args_list[1].args == (
            "team-xyz",
            "2026-03-01",
            "2026-08-31",
        )
        gateway_client.team_info.assert_called_once_with("team-xyz")

    def test_overview_limits_daily_preview_and_builds_show_all_url(self, project, gateway_client):
        Team.objects.create(project=project, litellm_team_id="team-xyz")
        daily_results = [
            {"date": f"2026-08-{day:02d}", "metrics": {"spend": day}} for day in range(1, 12)
        ]
        gateway_client.team_daily_activity.side_effect = [
            {"results": daily_results},
            {"results": daily_results},
        ]
        gateway_client.team_info.return_value = {"team_info": {}}

        with KeyService(gateway_client) as service:
            result = service.get_usage_overview(project, date(2026, 8, 1))

        assert len(result["daily_spend"]) == 11
        assert len(result["daily_spend_preview"]) == 10
        assert result["daily_spend_preview"][0] == {"label": "11 August 2026", "spend": 11}
        assert result["daily_show_all"] == {
            "shown": 10,
            "total": 11,
            "url": "?month=2026-08&daily=all",
        }

    def test_usage_by_key_maps_known_tokens_and_sorts_by_spend(
        self, project, user, gateway_client
    ):
        Team.objects.create(project=project, litellm_team_id="team-xyz")
        key = Key.objects.create(
            project=project,
            name="primary-key",
            litellm_alias="alias-1",
            litellm_secret="sk-1",
            litellm_token="known-token",
            masked_key="...1",
            created_by=user,
        )
        gateway_client.team_daily_activity.return_value = {
            "results": [
                {
                    "date": "2026-08-10",
                    "breakdown": {
                        "api_keys": {
                            "known-token": {"metrics": {"spend": 3.456}},
                            "deleted-token": {"metrics": {"spend": 9.001}},
                        }
                    },
                },
                {
                    "date": "2026-08-11",
                    "breakdown": {
                        "api_keys": {
                            "known-token": {"metrics": {"spend": 2}},
                        }
                    },
                },
            ]
        }

        with KeyService(gateway_client) as service:
            result = service.get_usage_by_key(project, date(2026, 8, 1))

        assert result == {
            "has_usage": True,
            "rows": [
                {"label": "deleted-token", "url": None, "spend": 9.0},
                {
                    "label": "primary-key",
                    "url": reverse(
                        "ai_gateway:key_detail", kwargs={"uuid": project.uuid, "pk": key.pk}
                    ),
                    "spend": 5.46,
                },
            ],
            "chart": None,
            "chart_label": "Spend per API key",
        }
        gateway_client.team_daily_activity.assert_called_once_with(
            "team-xyz",
            "2026-08-01",
            "2026-08-31",
        )

    def test_usage_by_model_aggregates_and_sorts_model_spend(self, project, gateway_client):
        Team.objects.create(project=project, litellm_team_id="team-xyz")
        gateway_client.team_daily_activity.return_value = {
            "results": [
                {
                    "date": "2026-08-10",
                    "breakdown": {
                        "models": {
                            "gpt-4": {"metrics": {"spend": 1.234}},
                            "claude-3": {"metrics": {"spend": 5}},
                        }
                    },
                },
                {
                    "date": "2026-08-11",
                    "breakdown": {"models": {"gpt-4": {"metrics": {"spend": 4}}}},
                },
            ]
        }

        with KeyService(gateway_client) as service:
            result = service.get_usage_by_model(project, date(2026, 8, 1))

        assert result == {
            "has_usage": True,
            "rows": [
                {"label": "gpt-4", "spend": 5.23},
                {"label": "claude-3", "spend": 5},
            ],
            "chart": None,
            "chart_label": "Spend per model",
        }

    def test_usage_by_key_returns_no_usage_without_gateway_team(self, project, gateway_client):
        with KeyService(gateway_client) as service:
            result = service.get_usage_by_key(project, date(2026, 8, 1))

        assert result == {"has_usage": False}
        gateway_client.team_daily_activity.assert_not_called()

    def test_usage_by_model_returns_no_usage_without_gateway_team(self, project, gateway_client):
        with KeyService(gateway_client) as service:
            result = service.get_usage_by_model(project, date(2026, 8, 1))

        assert result == {"has_usage": False}
        gateway_client.team_daily_activity.assert_not_called()

    def test_team_daily_activity_returns_results_list(self, gateway_client):
        team = Team(litellm_team_id="team-xyz")
        gateway_client.team_daily_activity.return_value = {"results": [{"date": "2026-08-01"}]}

        with KeyService(gateway_client) as service:
            result = service._team_daily_activity(
                team,
                date(2026, 8, 1),
                date(2026, 8, 31),
            )

        assert result == [{"date": "2026-08-01"}]
        gateway_client.team_daily_activity.assert_called_once_with(
            "team-xyz",
            "2026-08-01",
            "2026-08-31",
        )

    def test_team_daily_activity_defaults_to_empty_results(self, gateway_client):
        team = Team(litellm_team_id="team-xyz")
        gateway_client.team_daily_activity.return_value = {}

        with KeyService(gateway_client) as service:
            result = service._team_daily_activity(
                team,
                date(2026, 8, 1),
                date(2026, 8, 31),
            )

        assert result == []

    def test_team_max_budget_reads_team_info_budget(self, gateway_client):
        team = Team(litellm_team_id="team-xyz")
        gateway_client.team_info.return_value = {"team_info": {"max_budget": 123.45}}

        with KeyService(gateway_client) as service:
            result = service._team_max_budget(team)

        assert result == 123.45
        gateway_client.team_info.assert_called_once_with("team-xyz")

    def test_team_max_budget_defaults_to_none(self, gateway_client):
        team = Team(litellm_team_id="team-xyz")
        gateway_client.team_info.return_value = {"team_info": {}}

        with KeyService(gateway_client) as service:
            result = service._team_max_budget(team)

        assert result is None

    def test_daily_totals_skips_entries_without_dates_and_sorts_descending(self):
        result = KeyService._daily_totals(
            [
                {"date": "2026-08-10", "metrics": {"spend": 2.5}},
                {"metrics": {"spend": 99}},
                {"date": "2026-08-12", "metrics": {}},
            ]
        )

        assert result == [
            {"date": date(2026, 8, 12), "spend": 0},
            {"date": date(2026, 8, 10), "spend": 2.5},
        ]

    def test_monthly_totals_groups_by_month_and_sorts_descending(self):
        result = KeyService._monthly_totals(
            [
                {"date": "2026-08-10", "metrics": {"spend": 2.555}},
                {"date": "2026-08-12", "metrics": {"spend": 3.335}},
                {"date": "2026-07-01", "metrics": {}},
                {"metrics": {"spend": 99}},
            ]
        )

        assert result == [
            {"month": date(2026, 8, 1), "spend": 5.89},
            {"month": date(2026, 7, 1), "spend": 0},
        ]

    def test_breakdown_totals_sums_dimension_spend_and_treats_missing_spend_as_zero(self):
        result = KeyService._breakdown_totals(
            [
                {
                    "breakdown": {
                        "models": {
                            "gpt-4": {"metrics": {"spend": 1.5}},
                            "claude-3": {"metrics": {}},
                        }
                    }
                },
                {"breakdown": {"models": {"gpt-4": {"metrics": {"spend": 2}}}}},
                {"breakdown": {}},
            ],
            "models",
        )

        assert result == {"gpt-4": 3.5, "claude-3": 0}


class TestKeyServiceAllowedModelNames:
    def test_reads_access_group_models_for_a_team(self, project, gateway_client):
        Team.objects.create(project=project, litellm_team_id="team-xyz")
        gateway_client.team_info.return_value = {
            "team_info": {"access_group_models": ["gpt-4", "restricted-model"]}
        }

        with KeyService(gateway_client) as service:
            assert service._allowed_model_names(project) == {"gpt-4", "restricted-model"}

        gateway_client.list_models_for_access_group.assert_not_called()

    def test_reads_default_group_models_without_a_team(self, project, gateway_client, settings):
        settings.DEFAULT_ACCESS_GROUP_NAME = "generally-available-models"
        gateway_client.list_models_for_access_group.return_value = ["gpt-4"]

        with KeyService(gateway_client) as service:
            assert service._allowed_model_names(project) == {"gpt-4"}

        gateway_client.list_models_for_access_group.assert_called_once_with(
            "generally-available-models"
        )
        gateway_client.team_info.assert_not_called()


class TestKeyServiceReconcileTeamKeys:
    @pytest.fixture
    def team(self, project):
        """A gateway team whose only allowed model is gpt-4."""
        return Team.objects.create(project=project, litellm_team_id="team-xyz")

    @pytest.fixture
    def gpt4_only_client(self, gateway_client):
        """A client where gpt-4 is the sole allowed model for the team."""
        gateway_client.team_info.return_value = {"team_info": {"access_group_models": ["gpt-4"]}}
        return gateway_client

    def test_prunes_models_no_longer_allowed(self, team, gpt4_only_client):
        gpt4_only_client.list_team_keys.return_value = [
            {"token": "hash-1", "key_alias": "alias-1", "models": ["gpt-4", "restricted-model"]},
        ]

        with KeyService(gpt4_only_client) as service:
            updated, failed = service.reconcile_team_keys_to_allowed_models(team)

        gpt4_only_client.update_key_models.assert_called_once_with("hash-1", ["gpt-4"])
        assert updated == ["alias-1"]
        assert failed == []

    def test_leaves_allowed_only_keys_untouched(self, team, gpt4_only_client):
        gpt4_only_client.list_team_keys.return_value = [
            {"token": "hash-1", "key_alias": "alias-1", "models": ["gpt-4"]},
        ]

        with KeyService(gpt4_only_client) as service:
            updated, _failed = service.reconcile_team_keys_to_allowed_models(team)

        gpt4_only_client.update_key_models.assert_not_called()
        assert updated == []

    def test_sends_sentinel_when_all_models_pruned(self, team, gpt4_only_client):
        gpt4_only_client.list_team_keys.return_value = [
            {"token": "hash-1", "key_alias": "alias-1", "models": ["restricted-model"]},
        ]

        with KeyService(gpt4_only_client) as service:
            updated, _failed = service.reconcile_team_keys_to_allowed_models(team)

        gpt4_only_client.update_key_models.assert_called_once_with("hash-1", ["no-default-models"])
        assert updated == ["alias-1"]

    def test_best_effort_records_failures_and_continues(self, team, gpt4_only_client):
        gpt4_only_client.list_team_keys.return_value = [
            {"token": "hash-1", "key_alias": "alias-1", "models": ["restricted-model"]},
            {"token": "hash-2", "key_alias": "alias-2", "models": ["restricted-model"]},
        ]
        gpt4_only_client.update_key_models.side_effect = [AIGatewayAPIError(500, "boom"), None]

        with KeyService(gpt4_only_client) as service:
            updated, failed = service.reconcile_team_keys_to_allowed_models(team)

        assert failed == ["alias-1"]
        assert updated == ["alias-2"]
        assert gpt4_only_client.update_key_models.call_count == 2

    def test_failed_key_update_is_reported_to_sentry(self, team, gpt4_only_client):
        gpt4_only_client.list_team_keys.return_value = [
            {"token": "hash-1", "key_alias": "alias-1", "models": ["restricted-model"]},
        ]
        error = AIGatewayAPIError(500, "boom")
        gpt4_only_client.update_key_models.side_effect = error

        with (
            patch("ai_gateway.services.sentry_sdk.capture_exception") as capture_exception,
            KeyService(gpt4_only_client) as service,
        ):
            service.reconcile_team_keys_to_allowed_models(team)

        capture_exception.assert_called_once_with(error)

    def test_busts_model_cache_for_updated_key(self, project, user, team, gpt4_only_client):
        db_key = Key.objects.create(
            project=project,
            name="primary-key",
            litellm_alias="alias-1",
            litellm_secret="sk-1",
            litellm_token="hash-1",
            masked_key="...1",
            models=["gpt-4", "restricted-model"],
            created_by=user,
        )
        original_modified = db_key.modified
        gpt4_only_client.list_team_keys.return_value = [
            {"token": "hash-1", "key_alias": "alias-1", "models": ["gpt-4", "restricted-model"]},
        ]

        with KeyService(gpt4_only_client) as service:
            service.reconcile_team_keys_to_allowed_models(team, changed_by=user)

        db_key.refresh_from_db()
        assert db_key.modified > original_modified
        assert db_key.models == ["gpt-4"]

        latest_history = db_key.history.latest()
        assert latest_history.models == ["gpt-4"]
        assert latest_history.history_user == user
        assert latest_history.history_change_reason == (
            "Models reconciled after access group change"
        )


class TestKeyServiceAccessGroups:
    def test_list_access_groups_delegates_to_client(self, gateway_client):
        gateway_client.list_access_groups.return_value = [{"access_group_id": "ag-1"}]

        with KeyService(gateway_client) as service:
            groups = service.list_access_groups()

        assert groups == [{"access_group_id": "ag-1"}]
        gateway_client.list_access_groups.assert_called_once_with()

    def test_get_team_access_group_ids_delegates_to_client(self, gateway_client):
        gateway_client.get_team_access_group_ids.return_value = ["ag-1", "ag-2"]
        team = Team(litellm_team_id="team-abc-123")

        with KeyService(gateway_client) as service:
            ids = service.get_team_access_group_ids(team)

        assert ids == ["ag-1", "ag-2"]
        gateway_client.get_team_access_group_ids.assert_called_once_with("team-abc-123")

    def test_set_team_model_access_updates_groups_and_reconciles_keys(
        self, project, gateway_client
    ):
        team = Team.objects.create(project=project, litellm_team_id="team-abc-123")
        gateway_client.team_info.return_value = {"team_info": {"access_group_models": ["gpt-4"]}}
        gateway_client.list_team_keys.return_value = [
            {"token": "hash-1", "key_alias": "alias-1", "models": ["gpt-4", "restricted-model"]},
        ]

        with KeyService(gateway_client) as service:
            updated, failed = service.set_team_model_access(team, ["ag-1", "ag-2"])

        gateway_client.update_team_access_groups.assert_called_once_with(
            "team-abc-123", ["ag-1", "ag-2"]
        )
        gateway_client.update_key_models.assert_called_once_with("hash-1", ["gpt-4"])
        assert updated == ["alias-1"]
        assert failed == []
