from datetime import date
from decimal import Decimal
from unittest.mock import create_autospec, patch

import pytest
from django.urls import reverse

from ai_gateway.client import AIGatewayClient
from ai_gateway.forms import UsageDailyFilterForm, UsageMonthForm
from ai_gateway.services import UsageService


class FrozenDate(date):
    """A ``date`` subclass whose ``today()`` is fixed, so tests don't drift month to month."""

    @classmethod
    def today(cls):
        return cls(2026, 8, 20)


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


class TestUsageDailyFilterForm:
    @pytest.mark.parametrize("field", ["key", "model"])
    def test_rejects_choices_outside_the_selected_month(self, field):
        form = UsageDailyFilterForm(
            {field: "another-project-or-month"},
            key_choices=[("key-alias", "Key")],
            model_choices=[("model-name", "Model")],
        )

        assert not form.is_valid()
        assert field in form.errors

    def test_allows_empty_selections_and_renders_placeholders(self):
        form = UsageDailyFilterForm({}, key_choices=[], model_choices=[])

        assert form.is_valid()
        assert form.cleaned_data == {"key": "", "model": ""}
        assert form.fields["key"].choices == [("", "Select an API key")]
        assert form.fields["model"].choices == [("", "Select a model")]


class TestUsageServiceMonthChoices:
    def test_returns_months_from_team_creation_month(self, team, gateway_client):
        gateway_client.team_info.return_value = {
            "team_info": {"created_at": "2025-12-20T14:57:21.001000Z"}
        }

        with (
            patch("ai_gateway.services.date", FrozenDate),
            UsageService(gateway_client, team) as service,
        ):
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


class TestUsageServiceBudgetLimit:
    @pytest.mark.parametrize(
        ("spend", "budget", "expected"),
        [
            (Decimal("99.99"), Decimal("100"), False),
            (Decimal("100"), Decimal("100"), True),
            (Decimal("100.01"), Decimal("100"), True),
            (Decimal("100.01"), None, False),
        ],
    )
    def test_checks_spend_against_budget(self, team, gateway_client, spend, budget, expected):
        month = date(2026, 10, 1)

        with (
            UsageService(gateway_client, team) as service,
            patch.object(
                service, "get_budget_usage", return_value=(spend, budget)
            ) as get_budget_usage,
        ):
            assert service.is_at_budget_limit(month) is expected

        get_budget_usage.assert_called_once_with(month)


class TestUsageServiceGetUsage:
    def test_model_tokens_are_aggregated_for_monthly_and_daily_charts_only(
        self, team, gateway_client, key
    ):
        gateway_client.team_info.return_value = {
            "team_info": {"created_at": "2026-08-01T00:00:00"}
        }
        gateway_client.team_daily_activity.return_value = {
            "results": [
                {
                    "date": f"2026-08-{day:02d}",
                    "metrics": {"spend": day, "api_requests": day},
                    "breakdown": {
                        "model_groups": {
                            "model": {
                                "metrics": {
                                    "spend": day,
                                    "api_requests": day,
                                    "prompt_tokens": day * 100,
                                    "completion_tokens": day * 10,
                                }
                            }
                        },
                        "api_keys": {
                            "token": {
                                "metrics": {"spend": day, "api_requests": day},
                                "metadata": {"key_alias": key.litellm_alias},
                            }
                        },
                    },
                }
                for day in range(1, 4)
            ]
        }
        with UsageService(gateway_client, team) as service:
            result = service.get_usage(
                date(2026, 8, 1), key_alias=key.litellm_alias, model_name="model"
            )

        model = result["model_data"]
        assert model["rows"][0]["input_tokens"] == 600
        assert model["rows"][0]["output_tokens"] == 60
        assert model["tokens_chart_data"]["horizontal"] is True
        assert model["tokens_chart_data"]["series"] == [
            {"name": "Input tokens", "values": [600]},
            {"name": "Output tokens", "values": [60]},
        ]
        daily = model["daily"]
        assert [row["input_tokens"] for row in daily["rows"]] == [300, 200, 100]
        assert daily["tokens_chart_data"]["series"][0]["values"] == [100, 200, 300]
        assert daily["tokens_chart_data"]["chart_type"] == "line"
        assert daily["tokens_chart_data"]["value_format"] == "count"
        for data in (result["key_data"], result["key_data"]["daily"]):
            assert "tokens_chart_data" not in data
            assert "input_tokens" not in data["rows"][0]
            assert "output_tokens" not in data["rows"][0]
        assert "tokens_chart_data" not in result["overview_data"]
        gateway_client.team_daily_activity.assert_called_once()

    def test_selected_key_and_model_have_daily_usage_without_extra_gateway_calls(
        self, team, gateway_client, key
    ):
        gateway_client.team_info.return_value = {
            "team_info": {"created_at": "2026-08-01T00:00:00", "max_budget": 100}
        }
        gateway_client.team_daily_activity.return_value = {
            "results": [
                {
                    "date": f"2026-08-{day:02d}",
                    "metrics": {"spend": day, "api_requests": day * 10},
                    "breakdown": {
                        "api_keys": {
                            f"rotated-token-{day}": {
                                "metrics": {"spend": day, "api_requests": day * 10},
                                "metadata": {"key_alias": key.litellm_alias},
                            }
                        },
                        "model_groups": {
                            "gpt-4": {"metrics": {"spend": day, "api_requests": day * 10}}
                        },
                    },
                }
                for day in range(1, 4)
            ]
        }
        with UsageService(gateway_client, team) as service:
            result = service.get_usage(
                date(2026, 8, 1), key_alias=key.litellm_alias, model_name="gpt-4"
            )

        for dimension, selected, label in (
            ("key_data", key.litellm_alias, key.name),
            ("model_data", "gpt-4", "gpt-4"),
        ):
            daily = result[dimension]["daily"]
            assert daily["selected"] == selected
            assert daily["label"] == label
            assert [row["date"] for row in daily["rows"]] == [
                date(2026, 8, day) for day in (3, 2, 1)
            ]
            assert daily["chart_data"]["values"] == [1, 2, 3]
            assert daily["requests_chart_data"]["values"] == [10, 20, 30]
            assert daily["chart_data"]["chart_type"] == "line"
            assert "horizontal" not in daily["chart_data"]
        gateway_client.team_daily_activity.assert_called_once()

    def test_request_charts_share_spend_labels_and_use_count_values(
        self, team, gateway_client, key
    ):
        gateway_client.team_info.return_value = {
            "team_info": {"created_at": "2026-08-01T00:00:00", "max_budget": 100}
        }
        gateway_client.team_daily_activity.return_value = {
            "results": [
                {
                    "date": f"2026-08-{day:02d}",
                    "metrics": {"spend": day, "api_requests": day * 10},
                    "breakdown": {
                        "api_keys": {
                            key.litellm_token: {
                                "metrics": {"spend": day, "api_requests": day * 10},
                                "metadata": {"key_alias": key.litellm_alias},
                            }
                        },
                        "model_groups": {
                            "gpt-4": {"metrics": {"spend": day, "api_requests": day * 10}}
                        },
                    },
                }
                for day in range(1, 4)
            ]
        }

        with UsageService(gateway_client, team) as service:
            result = service.get_usage(date(2026, 8, 1))

        overview = result["overview_data"]
        for prefix, values in (("daily", [10, 20, 30]), ("monthly", [60])):
            requests = overview[f"{prefix}_requests_chart_data"]
            assert requests["labels"] == overview[f"{prefix}_chart_data"]["labels"]
            assert requests["values"] == values
            assert requests["value_format"] == "count"
            assert requests["value_axis_label"] == "Requests"
        assert overview["daily_requests_chart_data"]["chart_type"] == "line"
        for dimension in ("key_data", "model_data"):
            assert result[dimension]["requests_chart_data"]["values"] == [60]
            assert (
                result[dimension]["requests_chart_data"]["labels"]
                == result[dimension]["chart_data"]["labels"]
            )
        assert result["model_data"]["requests_chart_data"]["horizontal"] is True
        gateway_client.team_daily_activity.assert_called_once()

    def test_budget_usage_fetches_only_selected_month_without_rounding(self, team, gateway_client):
        gateway_client.team_info.return_value = {"team_info": {"max_budget": 100}}
        gateway_client.team_daily_activity.return_value = {
            "results": [
                {"date": "2026-10-01", "metrics": {"spend": 24.999}},
                {"date": "2026-10-02", "metrics": {"spend": 25}},
            ]
        }

        with UsageService(gateway_client, team) as service:
            spend, budget = service.get_budget_usage(date(2026, 10, 1))

        assert spend == Decimal("49.999")
        assert budget == Decimal("100")
        gateway_client.team_daily_activity.assert_called_once_with(
            "team-xyz", "2026-10-01", "2026-10-31"
        )

    def test_reuses_selected_activity_for_overview_key_and_model_data(
        self, team, gateway_client, key
    ):
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
                            "api_keys": {
                                key.litellm_token: {
                                    "metrics": {"spend": 10},
                                    "metadata": {"key_alias": key.litellm_alias},
                                }
                            },
                            "model_groups": {"gpt-4": {"metrics": {"spend": 10}}},
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
                "id": key.litellm_alias,
                "label": "primary-key",
                "url": reverse(
                    "ai_gateway:key_detail", kwargs={"uuid": team.project.uuid, "pk": key.pk}
                ),
                "spend": 10,
                "requests": None,
            }
        ]
        assert result["key_data"]["chart_name"] == "key-spend"
        assert result["key_data"]["chart_data"] == {
            "labels": ["primary-key"],
            "values": [10],
            "category_axis_label": "API Key",
            "value_axis_label": "Spend ($)",
        }
        assert result["model_data"]["rows"] == [
            {
                "id": "gpt-4",
                "label": "gpt-4",
                "spend": 10,
                "requests": None,
                "input_tokens": None,
                "output_tokens": None,
            }
        ]
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
        assert result["overview_data"]["daily_requests_chart_data"]["chart_type"] == "line"
        assert result["overview_data"]["monthly_requests_chart_data"]["chart_type"] == "line"

    def test_overview_reports_no_usage_when_team_has_no_spend(self, team, gateway_client):
        gateway_client.team_info.return_value = {
            "team_info": {
                "created_at": "2026-01-15T10:00:00.000000Z",
                "max_budget": 100,
            }
        }
        gateway_client.team_daily_activity.side_effect = [
            {"results": []},
            {"results": []},
        ]

        with UsageService(gateway_client, team) as service:
            result = service.get_usage(date(2026, 8, 1))

        assert result["overview_data"] == {"has_usage": False}

    def test_excludes_keys_and_models_with_zero_total_spend(self, team, gateway_client, key):
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
                            "api_keys": {
                                key.litellm_token: {
                                    "metrics": {"spend": 10},
                                    "metadata": {"key_alias": key.litellm_alias},
                                },
                                "zero-key-token": {
                                    "metrics": {"spend": 0, "api_requests": 100},
                                    "metadata": {"key_alias": "zero-key"},
                                },
                                "cancelling-token": {
                                    "metrics": {"spend": 5},
                                    "metadata": {"key_alias": "cancelling-key"},
                                },
                            },
                            "model_groups": {
                                "gpt-4": {"metrics": {"spend": 10}},
                                "unused-model": {"metrics": {"spend": 0, "api_requests": 100}},
                            },
                        },
                    },
                    {
                        "date": "2026-08-11",
                        "metrics": {"spend": -5},
                        "breakdown": {
                            "api_keys": {
                                "cancelling-token": {
                                    "metrics": {"spend": -5},
                                    "metadata": {"key_alias": "cancelling-key"},
                                },
                            },
                            "model_groups": {},
                        },
                    },
                ]
            },
            {"results": []},
        ]

        with UsageService(gateway_client, team) as service:
            result = service.get_usage(date(2026, 8, 1))

        assert result["key_data"]["rows"] == [
            {
                "id": key.litellm_alias,
                "label": "primary-key",
                "url": reverse(
                    "ai_gateway:key_detail", kwargs={"uuid": team.project.uuid, "pk": key.pk}
                ),
                "spend": 10,
                "requests": None,
            }
        ]
        assert result["model_data"]["rows"] == [
            {
                "id": "gpt-4",
                "label": "gpt-4",
                "spend": 10,
                "requests": None,
                "input_tokens": None,
                "output_tokens": None,
            }
        ]

    @pytest.mark.parametrize("missing_field", ["prompt_tokens", "completion_tokens"])
    @pytest.mark.parametrize("missing_value", [None, "absent"])
    def test_partial_token_counts_stay_unavailable_when_other_counts_arrive(
        self, team, gateway_client, missing_field, missing_value
    ):
        partial = {"spend": 1, "api_requests": 1, "prompt_tokens": 5, "completion_tokens": 7}
        if missing_value == "absent":
            partial.pop(missing_field)
        else:
            partial[missing_field] = missing_value
        activity = [
            {
                "date": f"2026-08-{day:02d}",
                "breakdown": {"model_groups": {"model": {"metrics": metrics}}},
            }
            for day, metrics in (
                (1, {"spend": 1, "api_requests": 1, "prompt_tokens": 10, "completion_tokens": 20}),
                (2, partial),
                (2, {"spend": 1, "api_requests": 1, "prompt_tokens": 1, "completion_tokens": 2}),
            )
        ]
        with UsageService(gateway_client, team) as service:
            monthly = service._build_model_usage(activity)
            daily = service._build_daily_usage(
                activity, "model_groups", monthly["rows"], "model", date(2026, 8, 1)
            )

        unavailable = "input_tokens" if missing_field == "prompt_tokens" else "output_tokens"
        known = "output_tokens" if unavailable == "input_tokens" else "input_tokens"
        assert monthly["rows"][0][unavailable] is None
        assert monthly["rows"][0][known] == (29 if known == "output_tokens" else 16)
        assert daily["rows"][0][unavailable] is None
        assert daily["rows"][0][known] == (9 if known == "output_tokens" else 6)
        assert monthly["tokens_chart_data"] is None
        assert daily["tokens_chart_data"] is None

    @pytest.mark.parametrize("days", [1, 2, 3])
    def test_zero_token_counts_are_valid_and_daily_charts_follow_the_point_threshold(
        self, team, gateway_client, days
    ):
        activity = [
            {
                "date": f"2026-08-{day:02d}",
                "breakdown": {
                    "model_groups": {
                        "model": {
                            "metrics": {
                                "spend": 1,
                                "api_requests": 1,
                                "prompt_tokens": 0,
                                "completion_tokens": 0,
                                "total_tokens": 9999,
                            }
                        }
                    }
                },
            }
            for day in range(1, days + 1)
        ]
        with UsageService(gateway_client, team) as service:
            monthly = service._build_model_usage(activity)
            daily = service._build_daily_usage(
                activity, "model_groups", monthly["rows"], "model", date(2026, 8, 1)
            )

        assert monthly["rows"][0]["input_tokens"] == 0
        assert monthly["rows"][0]["output_tokens"] == 0
        assert daily["tokens_chart_data"]["chart_type"] == ("line" if days > 2 else "bar")
        assert daily["tokens_chart_data"]["horizontal"] is False
        for series in daily["tokens_chart_data"]["series"]:
            assert series["values"] == [0] * days

    def test_monthly_token_series_keep_spend_order_and_omit_zero_spend_models(
        self, team, gateway_client
    ):
        activity = [
            {
                "breakdown": {
                    "model_groups": {
                        name: {
                            "metrics": {
                                "spend": spend,
                                "api_requests": 1,
                                "prompt_tokens": input_tokens,
                                "completion_tokens": input_tokens * 2,
                            }
                        }
                        for name, spend, input_tokens in (
                            ("expensive", 10, 1),
                            ("busy", 1, 100),
                            ("free", 0, 1000),
                        )
                    }
                }
            }
        ]
        with UsageService(gateway_client, team) as service:
            monthly = service._build_model_usage(activity)

        tokens = monthly["tokens_chart_data"]
        assert tokens["labels"] == monthly["chart_data"]["labels"] == ["busy", "expensive"]
        assert tokens["series"] == [
            {"name": "Input tokens", "values": [100, 1]},
            {"name": "Output tokens", "values": [200, 2]},
        ]

    @pytest.mark.parametrize("selected", ["", "missing", "excluded"])
    def test_daily_choices_follow_monthly_eligibility_and_invalid_selections_reset(
        self, team, gateway_client, selected
    ):
        gateway_client.team_info.return_value = {
            "team_info": {"created_at": "2026-08-01T00:00:00"}
        }
        gateway_client.team_daily_activity.return_value = {
            "results": [
                {
                    "date": "2026-08-01",
                    "metrics": {"spend": 3, "api_requests": 10},
                    "breakdown": {
                        "model_groups": {
                            "Zulu": {"metrics": {"spend": 2, "api_requests": 1}},
                            "alpha": {"metrics": {"spend": 1, "api_requests": 2}},
                            "excluded": {"metrics": {"spend": 0, "api_requests": 7}},
                        }
                    },
                }
            ]
        }
        with UsageService(gateway_client, team) as service:
            result = service.get_usage(date(2026, 8, 1), key_alias=selected, model_name=selected)

        assert result["model_data"]["daily"]["choices"] == [("alpha", "alpha"), ("Zulu", "Zulu")]
        assert [row["id"] for row in result["model_data"]["rows"]] == ["Zulu", "alpha"]
        for dimension in ("key_data", "model_data"):
            assert result[dimension]["daily"]["selected"] == ""
            assert result[dimension]["daily"]["rows"] == []
        gateway_client.team_daily_activity.assert_called_once()

    @pytest.mark.parametrize("dimension", ["api_keys", "model_groups"])
    def test_daily_breakdowns_combine_dates_and_preserve_zero_and_unknown_counts(
        self, team, gateway_client, dimension
    ):
        activity = [
            {
                "date": f"2026-08-{day:02d}",
                "breakdown": {
                    dimension: {
                        "chosen" if dimension == "model_groups" else f"token-{index}": {
                            "metrics": metrics,
                            "metadata": {"key_alias": "chosen"},
                        },
                        "other": {
                            "metrics": {"spend": 100, "api_requests": 1000},
                            "metadata": {"key_alias": "other"},
                        },
                    }
                },
            }
            for index, (day, metrics) in enumerate(
                [
                    (1, {"spend": 2, "api_requests": 3}),
                    (1, {"spend": 1, "api_requests": 4}),
                    (2, {"spend": 0, "api_requests": 0}),
                    (3, {"spend": 0.001, "api_requests": None}),
                ]
            )
        ]
        with UsageService(gateway_client, team) as service:
            daily = service._build_daily_usage(
                activity,
                dimension,
                [{"id": "chosen", "label": "Chosen name"}],
                "chosen",
                date(2026, 8, 1),
            )

        assert daily["label"] == "Chosen name"
        assert [row["spend"] for row in daily["rows"]] == [0.001, 0, 3]
        assert [row["requests"] for row in daily["rows"]] == [None, 0, 7]
        assert daily["requests_chart_data"] is None
        assert daily["chart_data"]["labels"] == ["1", "2", "3"]
        assert daily["chart_data"]["values"] == [3, 0, 0.001]

    def test_daily_drill_down_includes_all_recorded_dates_in_the_selected_month(
        self, team, gateway_client
    ):
        activity = [
            {
                "date": f"2026-08-{day:02d}",
                "breakdown": {
                    "model_groups": {"chosen": {"metrics": {"spend": 1, "api_requests": day}}}
                },
            }
            for day in range(1, 14)
        ]
        activity.extend(
            [
                {"date": "2026-07-31", "breakdown": activity[0]["breakdown"]},
                {"breakdown": activity[0]["breakdown"]},
            ]
        )
        with UsageService(gateway_client, team) as service:
            daily = service._build_daily_usage(
                activity,
                "model_groups",
                [{"id": "chosen", "label": "Chosen"}],
                "chosen",
                date(2026, 8, 1),
            )

        assert len(daily["rows"]) == 13
        assert daily["requests_chart_data"]["values"] == list(range(1, 14))
        assert sum(row["spend"] for row in daily["rows"]) == 13

    @pytest.mark.parametrize("metrics", [{"spend": 2}, {"spend": 2, "api_requests": None}])
    def test_incomplete_breakdown_counts_are_unavailable(self, team, gateway_client, metrics):
        activity = [
            {
                "breakdown": {
                    "api_keys": {
                        "old-token": {
                            "metrics": {"spend": 1, "api_requests": 10},
                            "metadata": {"key_alias": "rotated-key"},
                        },
                        "new-token": {
                            "metrics": metrics,
                            "metadata": {"key_alias": "rotated-key"},
                        },
                    },
                    "model_groups": {"model": {"metrics": metrics}},
                }
            }
        ]
        with UsageService(gateway_client, team) as service:
            key_data = service._build_key_usage(activity)
            model_data = service._build_model_usage(activity)

        for data in (key_data, model_data):
            assert data["rows"][0]["requests"] is None
            assert data["requests_chart_data"] is None
        assert key_data["rows"][0]["spend"] == 3

    def test_regenerated_keys_and_models_keep_spend_order_for_requests(
        self, team, gateway_client, key
    ):
        activity = [
            {
                "breakdown": {
                    "api_keys": {
                        f"token-{day}": {
                            "metrics": {"spend": 10, "api_requests": 1},
                            "metadata": {"key_alias": key.litellm_alias},
                        },
                        "busy-token": {
                            "metrics": {"spend": 1, "api_requests": 100},
                            "metadata": {"key_alias": "busy-key"},
                        },
                    },
                    "model_groups": {
                        "expensive": {"metrics": {"spend": 10, "api_requests": 1}},
                        "busy": {"metrics": {"spend": 1, "api_requests": 100}},
                    },
                }
            }
            for day in range(2)
        ]
        with UsageService(gateway_client, team) as service:
            data_by_dimension = (
                service._build_key_usage(activity),
                service._build_model_usage(activity),
            )

        for data in data_by_dimension:
            assert [row["requests"] for row in data["rows"]] == [2, 200]
            assert data["requests_chart_data"]["values"] == [200, 2]
            assert data["requests_chart_data"]["labels"] == data["chart_data"]["labels"]
        assert data_by_dimension[0]["rows"][0]["label"] == key.name

    def test_zero_request_counts_are_valid_chart_values(self, team, gateway_client):
        activity = [
            {
                "breakdown": {
                    "model_groups": {"model": {"metrics": {"spend": 1, "api_requests": 0}}}
                }
            }
        ]
        with UsageService(gateway_client, team) as service:
            data = service._build_model_usage(activity)

        assert data["requests_chart_data"]["values"] == [0]

    def test_daily_request_chart_includes_days_outside_the_table_preview(
        self, team, gateway_client
    ):
        gateway_client.team_info.return_value = {
            "team_info": {"created_at": "2026-08-01T00:00:00", "max_budget": 100}
        }
        gateway_client.team_daily_activity.return_value = {
            "results": [
                {"date": f"2026-08-{day:02d}", "metrics": {"spend": 1, "api_requests": day}}
                for day in range(1, 14)
            ]
        }
        with UsageService(gateway_client, team) as service:
            overview = service.get_usage(date(2026, 8, 1))["overview_data"]

        assert len(overview["daily_spend_preview"]) == 10
        assert overview["daily_requests_chart_data"]["values"] == list(range(1, 14))
        assert overview["monthly_requests_chart_data"]["values"] == [91]

    def test_monthly_request_chart_uses_history_in_chronological_order(self, team, gateway_client):
        gateway_client.team_info.return_value = {
            "team_info": {"created_at": "2026-07-01T00:00:00", "max_budget": 100}
        }
        selected = {"date": "2026-08-10", "metrics": {"spend": 1, "api_requests": 7}}
        gateway_client.team_daily_activity.side_effect = [
            {"results": [selected]},
            {
                "results": [
                    selected,
                    {"date": "2026-07-20", "metrics": {"spend": 1, "api_requests": 3}},
                    {"date": "2026-07-01", "metrics": {"spend": 1, "api_requests": 2}},
                ]
            },
        ]
        with UsageService(gateway_client, team) as service:
            overview = service.get_usage(date(2026, 8, 1))["overview_data"]

        assert overview["monthly_requests_chart_data"]["labels"] == ["July 2026", "August 2026"]
        assert overview["monthly_requests_chart_data"]["values"] == [5, 7]
        assert "chart_type" not in overview["monthly_requests_chart_data"]
        assert gateway_client.team_daily_activity.call_count == 2
