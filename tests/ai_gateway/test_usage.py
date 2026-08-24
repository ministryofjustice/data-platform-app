from datetime import date
from unittest.mock import create_autospec

import pytest
from django.urls import reverse

from ai_gateway.client import AIGatewayClient
from ai_gateway.forms import UsageMonthForm
from ai_gateway.models import Key
from ai_gateway.services import UsageService


@pytest.fixture
def gateway_client():
    """An autospecced AIGatewayClient with default successful responses."""
    return create_autospec(AIGatewayClient, instance=True)


class TestUsageMonthForm:
    def test_returns_date_for_valid_choice(self):
        form = UsageMonthForm(
            {"month": "2026-01"},
            month_choices=[date(2026, 1, 1), date(2025, 12, 1)],
        )

        assert form.is_valid()
        assert form.cleaned_data["month"] == date(2026, 1, 1)

    @pytest.mark.parametrize("value", ["banana", "2026-13", "01-2026", "2025-12"])
    def test_rejects_malformed_and_unavailable_months(self, value):
        form = UsageMonthForm({"month": value}, month_choices=[date(2026, 1, 1)])

        assert not form.is_valid()

    def test_allows_missing_month(self):
        form = UsageMonthForm({}, month_choices=[date(2026, 1, 1)])

        assert form.is_valid()
        assert form.cleaned_data["month"] == ""

    def test_builds_month_choices_with_display_labels(self):
        form = UsageMonthForm(
            month_choices=[date(2026, 8, 1), date(2026, 7, 1)],
        )

        assert form.fields["month"].choices == [
            ("2026-08", "August 2026"),
            ("2026-07", "July 2026"),
        ]


class TestUsageServiceMonthChoices:
    def test_returns_months_from_team_creation_month(self, team, gateway_client):
        gateway_client.team_info.return_value = {
            "team_info": {"created_at": "2025-12-20T14:57:21.001000Z"}
        }

        with UsageService(gateway_client, team) as service:
            choices = service.get_usage_month_choices()

        assert choices == [
            date(2026, 8, 1),
            date(2026, 7, 1),
            date(2026, 6, 1),
            date(2026, 5, 1),
            date(2026, 4, 1),
            date(2026, 3, 1),
            date(2026, 2, 1),
            date(2026, 1, 1),
            date(2025, 12, 1),
        ]
        gateway_client.team_info.assert_called_once_with("team-xyz")


class TestUsageServiceGetUsage:
    def test_reuses_selected_activity_for_overview_key_and_model_data(
        self, team, user, gateway_client
    ):
        key = Key.objects.create(
            project=team.project,
            name="primary-key",
            litellm_alias="alias-1",
            litellm_secret="sk-1",
            litellm_token="known-token",
            masked_key="...1",
            created_by=user,
        )
        gateway_client.team_info.return_value = {
            "team_info": {
                "created_at": "2026-01-15T10:00:00.000000Z",
                "max_budget": 100,
            }
        }
        gateway_client.team_daily_activity.side_effect = [
            {
                "results": [
                    {
                        "date": "2026-08-10",
                        "metrics": {"spend": 10},
                        "breakdown": {
                            "api_keys": {"known-token": {"metrics": {"spend": 10}}},
                            "models": {"gpt-4": {"metrics": {"spend": 10}}},
                        },
                    }
                ]
            },
            {"results": []},
        ]

        with UsageService(gateway_client, team) as service:
            result = service.get_usage(date(2026, 8, 1))

        assert result["overview_data"]["total_spend"] == 10
        assert result["overview_data"]["daily_chart_name"] == "daily-spend"
        assert result["overview_data"]["daily_chart_data"] == {
            "labels": ["10"],
            "values": [10],
            "category_axis_label": "Day (August 2026)",
            "value_axis_label": "Spend ($)",
        }
        assert result["overview_data"]["monthly_chart_name"] == "monthly-spend"
        assert result["overview_data"]["monthly_chart_data"] == {
            "labels": [],
            "values": [],
            "category_axis_label": "Month",
            "value_axis_label": "Spend ($)",
        }
        assert result["key_data"]["rows"] == [
            {
                "label": "primary-key",
                "url": reverse(
                    "ai_gateway:key_detail", kwargs={"uuid": team.project.uuid, "pk": key.pk}
                ),
                "spend": 10,
            }
        ]
        assert result["key_data"]["chart_name"] == "key-spend"
        assert result["key_data"]["chart_data"] == {
            "labels": ["primary-key"],
            "values": [10],
            "category_axis_label": "API Key",
            "value_axis_label": "Spend ($)",
        }
        assert result["model_data"]["rows"] == [{"label": "gpt-4", "spend": 10}]
        assert result["model_data"]["chart_name"] == "model-spend"
        assert result["model_data"]["chart_data"] == {
            "labels": ["gpt-4"],
            "values": [10],
            "category_axis_label": "Model",
            "value_axis_label": "Spend ($)",
            "horizontal": True,
        }
        assert gateway_client.team_daily_activity.call_count == 2
        gateway_client.team_info.assert_called_once_with("team-xyz")

    def test_daily_and_monthly_charts_use_line_type_beyond_min_points(self, team, gateway_client):
        gateway_client.team_info.return_value = {
            "team_info": {
                "created_at": "2026-03-01T10:00:00.000000Z",
                "max_budget": 100,
            }
        }
        gateway_client.team_daily_activity.side_effect = [
            {
                "results": [
                    {"date": "2026-08-10", "metrics": {"spend": 10.12}},
                    {"date": "2026-08-11", "metrics": {"spend": 2.22}},
                    {"date": "2026-08-12", "metrics": {"spend": 3.0}},
                ]
            },
            {
                "results": [
                    {"date": "2026-06-01", "metrics": {"spend": 1.0}},
                    {"date": "2026-07-01", "metrics": {"spend": 2.0}},
                    {"date": "2026-08-10", "metrics": {"spend": 15.34}},
                ]
            },
        ]

        with UsageService(gateway_client, team) as service:
            result = service.get_usage(date(2026, 8, 1))

        assert result["overview_data"]["daily_chart_data"]["chart_type"] == "line"
        assert result["overview_data"]["monthly_chart_data"]["chart_type"] == "line"
