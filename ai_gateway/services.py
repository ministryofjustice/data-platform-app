"""Service layer for AI Gateway key operations."""

from __future__ import annotations

import calendar
import secrets
from datetime import date, datetime
from decimal import Decimal
from math import isfinite
from typing import Any, NotRequired, TypedDict

import sentry_sdk
import structlog
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.text import slugify

from ai_gateway.client import AIGatewayClient
from ai_gateway.exceptions import AIGatewayAPIError, AIGatewayError
from ai_gateway.filtering import exclude_catalogue_models
from ai_gateway.models import BudgetAlert, BudgetAlertNotification, Key, Team
from data_platform_app.services import GovUKNotificationsService
from data_platform_app.utils import build_base_url
from projects.models import Project
from users.models import User

DAILY_SPEND_PREVIEW_COUNT = 10
LINE_CHART_MIN_POINTS = 2
MAX_BUDGET_ALERT_THRESHOLD = 100
BUDGET_ALERT_THRESHOLDS = [90, 50]
_ESTIMATE_TOO_LARGE = (
    "The estimated cost is too large to calculate. Enter smaller token or request values."
)

logger = structlog.get_logger(__name__)


class _UsageTotals(TypedDict):
    spend: float
    requests: int | None
    input_tokens: NotRequired[int | None]
    output_tokens: NotRequired[int | None]


def budget_alert_threshold(spend: Decimal, budget: Decimal | None) -> int | None:
    """Return the highest threshold reached, without rounding the spend."""
    if not budget:
        return None

    percent_used = (spend / budget) * 100
    if percent_used >= MAX_BUDGET_ALERT_THRESHOLD:
        return MAX_BUDGET_ALERT_THRESHOLD

    for threshold in BUDGET_ALERT_THRESHOLDS:
        if percent_used > threshold:
            return threshold

    return None


@transaction.atomic
def record_budget_alert(
    project: Project, threshold: int, spend: Decimal, budget: Decimal
) -> BudgetAlert | None:
    """Record a new threshold for this month's budget and snapshot its eligible recipients."""
    month = timezone.localdate().replace(day=1)
    if project.budget_alerts.filter(
        period_start=month, budget=budget, threshold_percent__gte=threshold
    ).exists():
        return None

    alert, created = BudgetAlert.objects.get_or_create(
        project=project,
        period_start=month,
        budget=budget,
        threshold_percent=threshold,
        defaults={"spend": spend},
    )
    if not created:
        return None

    memberships = None
    if threshold >= MAX_BUDGET_ALERT_THRESHOLD:
        memberships = project.memberships.select_related("user")
    else:
        memberships = project.memberships.can_manage_api_keys().select_related("user")

    for membership in memberships:
        alert.notifications.get_or_create(
            email_address=membership.user.email,
            defaults={"recipient": membership.user},
        )

    return alert


@transaction.atomic
def send_budget_alert_notification(notification: BudgetAlertNotification) -> None:
    """Submit a selected warning; failures propagate and remain retryable."""
    notification = BudgetAlertNotification.objects.select_for_update().get(pk=notification.pk)
    alert = notification.alert
    if notification.sent_at:
        return

    limit_hit = alert.threshold_percent >= MAX_BUDGET_ALERT_THRESHOLD
    if limit_hit:
        template_id = settings.NOTIFY_BUDGET_LIMIT_HIT_TEMPLATE_ID
        setting_name = "NOTIFY_BUDGET_LIMIT_HIT_TEMPLATE_ID"
    else:
        template_id = settings.NOTIFY_BUDGET_ALERT_TEMPLATE_ID
        setting_name = "NOTIFY_BUDGET_ALERT_TEMPLATE_ID"
    if not template_id:
        raise ImproperlyConfigured(f"Missing Notify settings: {setting_name}")

    personalisation = {
        "project_name": alert.project.name,
        "project_url": (
            f"{build_base_url(settings.APP_ENV)}"
            f"{reverse('ai_gateway:usage', kwargs={'uuid': alert.project.uuid})}"
        ),
    }
    if not limit_hit:
        personalisation["threshold_percent"] = str(alert.threshold_percent)

    notification.notify_notification_id = GovUKNotificationsService.from_settings().send_email(
        email_address=notification.email_address,
        template_id=template_id,
        personalisation=personalisation,
    )
    notification.sent_at = timezone.now()
    notification.save(update_fields=["sent_at", "notify_notification_id", "modified"])


def previous_month(value: date) -> date:
    if value.month == 1:
        return date(year=value.year - 1, month=12, day=1)

    return date(year=value.year, month=value.month - 1, day=1)


def estimate_costs(
    *,
    usage_period: str,
    model_rows: list[dict[str, Any]],
    available_models: list[dict[str, Any]],
) -> dict[str, Any]:
    """Estimate spend for each model row and the overall total.

    ``model_rows`` are cleaned_data dicts from ModelUsageRateForm; ``usage_period``
    is "daily" or "monthly" from UsagePeriodForm (does not impact calculation).
    Raises ValidationError when the inputs cannot produce finite float costs.
    """
    models_by_name = {model["model_name"]: model for model in available_models}

    rows = []
    total_per_request = 0.0
    total_cost = 0.0

    for row in model_rows:
        model = models_by_name.get(row["model"])
        if not model:
            continue

        try:
            input_cost = (
                (model.get("input_cost_per_million") or 0) * row["input_tokens"] / 1_000_000
            )
            output_cost = (
                (model.get("output_cost_per_million") or 0) * row["output_tokens"] / 1_000_000
            )
            per_request_cost = input_cost + output_cost
            row_cost = per_request_cost * row["requests_per_period"]
            total_per_request += per_request_cost
            total_cost += row_cost
        except OverflowError as error:
            raise ValidationError(_ESTIMATE_TOO_LARGE, code="estimate_too_large") from error

        if not all(
            isfinite(value)
            for value in (per_request_cost, row_cost, total_per_request, total_cost)
        ):
            raise ValidationError(_ESTIMATE_TOO_LARGE, code="estimate_too_large")
        rows.append(
            {
                "model_name": model["display_name"],
                "provider": model["provider"],
                "per_request_cost": round(per_request_cost, 4),
                "cost": round(row_cost, 4),
            }
        )

    return {
        "usage_period": usage_period,
        "rows": rows,
        "total_per_request": round(total_per_request, 4),
        "total_cost": round(total_cost, 4),
    }


class UsageService:
    """Coordinates AI Gateway usage reporting for a team."""

    def __init__(self, client: AIGatewayClient, team: Team) -> None:
        self._client = client
        self._team = team

    @classmethod
    def from_settings(cls, team: Team) -> UsageService:
        return cls(AIGatewayClient.from_settings(), team)

    def __enter__(self) -> UsageService:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    @cached_property
    def team_info(self) -> dict[str, Any]:
        return self._client.team_info(self._team.litellm_team_id).get("team_info", {})

    @cached_property
    def usage_start(self) -> date:
        """
        Uses the Team created_at timestamp to determine when usage data should start from
        """
        return datetime.fromisoformat(self.team_info.get("created_at")).date().replace(day=1)

    def get_usage_month_choices(self) -> list[date]:
        """Return months from the team's creation month to the current month."""
        choices = []
        month = date.today().replace(day=1)
        while month >= self.usage_start:
            choices.append(month)
            month = previous_month(month)
        return choices

    def get_usage(
        self, month: date, *, key_alias: str = "", model_name: str = ""
    ) -> dict[str, Any]:
        """Return monthly usage and daily drill-downs for eligible key/model selections."""
        month_start = month.replace(day=1)
        month_end = month.replace(day=calendar.monthrange(month.year, month.month)[1])
        month_spend = self._team_daily_activity(month_start, month_end)

        full_spend_history = month_spend
        if self.usage_start < month_start:
            full_spend_history = self._team_daily_activity(self.usage_start, month_end)

        key_data = self._build_key_usage(month_spend)
        model_data = self._build_model_usage(month_spend)
        key_data["daily"] = self._build_daily_usage(
            month_spend, "api_keys", key_data["rows"], key_alias, month_start
        )
        model_data["daily"] = self._build_daily_usage(
            month_spend, "model_groups", model_data["rows"], model_name, month_start
        )

        return {
            "overview_data": self._build_overview(
                month_start,
                month_spend,
                full_spend_history,
            ),
            "key_data": key_data,
            "model_data": model_data,
        }

    def get_budget_usage(self, month: date) -> tuple[Decimal, Decimal | None]:
        """Return monthly spend and budget without building the usage report."""
        month_start = month.replace(day=1)
        month_end = month_start.replace(day=calendar.monthrange(month.year, month.month)[1])
        daily_rows = self._daily_rows(self._team_daily_activity(month_start, month_end))
        spend = sum((Decimal(str(row["spend"])) for row in daily_rows), Decimal("0"))
        budget = self.team_info["max_budget"]
        return spend, None if budget is None else Decimal(str(budget))

    def is_at_budget_limit(self, month: date) -> bool:
        """Return True if the team is at or over budget for the month."""
        spend, budget = self.get_budget_usage(month)
        if budget is None:
            return False
        return spend >= budget

    def _build_overview(
        self,
        month_start: date,
        daily_results: list[dict[str, Any]],
        full_spend_history: list[dict[str, Any]],
    ) -> dict[str, Any]:
        daily_rows = self._daily_rows(daily_results)
        total_spend = round(sum(day["spend"] for day in daily_rows), 2)
        total_requests = sum(day["requests"] for day in daily_rows)

        if not total_spend:
            return {"has_usage": False}

        monthly_rows = self._monthly_rows(full_spend_history)

        max_budget = self.team_info.get("max_budget")
        budget_remaining = None if max_budget is None else round(max_budget - total_spend, 2)
        percent_used = None if not max_budget else round((total_spend / max_budget) * 100, 1)
        alert_threshold = None
        if month_start == timezone.localdate().replace(day=1):
            alert_threshold = budget_alert_threshold(
                spend=sum((Decimal(str(day["spend"])) for day in daily_rows), Decimal("0")),
                budget=None if max_budget is None else Decimal(str(max_budget)),
            )

        daily_show_all = None
        if len(daily_rows) > DAILY_SPEND_PREVIEW_COUNT:
            daily_show_all = {
                "shown": DAILY_SPEND_PREVIEW_COUNT,
                "total": len(daily_rows),
                "url": f"?month={month_start.strftime('%Y-%m')}&daily=all",
            }

        daily_chart_rows = [{**row, "label": row["date"].strftime("%-d")} for row in daily_rows]
        daily_chart_data = self._create_chart_data(
            daily_chart_rows,
            "label",
            "spend",
            f"Day ({month_start.strftime('%B %Y')})",
            "Spend ($)",
            reverse=True,
        )
        daily_requests_chart_data = self._create_requests_chart_data(
            daily_chart_rows, f"Day ({month_start.strftime('%B %Y')})"
        )
        if len(daily_rows) > LINE_CHART_MIN_POINTS:
            daily_chart_data["chart_type"] = "line"
            if daily_requests_chart_data:
                daily_requests_chart_data["chart_type"] = "line"

        monthly_chart_data = self._create_chart_data(
            monthly_rows, "label", "spend", "Month", "Spend ($)", reverse=True
        )
        monthly_requests_chart_data = self._create_requests_chart_data(monthly_rows, "Month")
        if len(monthly_rows) > LINE_CHART_MIN_POINTS:
            monthly_chart_data["chart_type"] = "line"
            if monthly_requests_chart_data:
                monthly_requests_chart_data["chart_type"] = "line"

        return {
            "has_usage": True,
            "total_spend": total_spend,
            "total_requests": total_requests,
            "max_budget": max_budget,
            "budget_remaining": budget_remaining,
            "percent_used": percent_used,
            "budget_alert_threshold": alert_threshold,
            "daily_spend": daily_rows,
            "daily_spend_preview": daily_rows[:DAILY_SPEND_PREVIEW_COUNT],
            "daily_show_all": daily_show_all,
            "daily_chart_data": daily_chart_data,
            "daily_chart_name": "daily-spend",
            "daily_chart_label": f"Daily spend for {month_start.strftime('%B %Y')}",
            "daily_requests_chart_data": daily_requests_chart_data,
            "daily_requests_chart_name": "daily-requests",
            "daily_requests_chart_label": f"Daily requests for {month_start.strftime('%B %Y')}",
            "monthly_spend_rows": monthly_rows,
            "monthly_chart_name": "monthly-spend",
            "monthly_chart_data": monthly_chart_data,
            "monthly_requests_chart_data": monthly_requests_chart_data,
            "monthly_requests_chart_name": "monthly-requests",
            "monthly_requests_chart_label": "Monthly requests",
        }

    @staticmethod
    def _create_chart_data(
        rows: list[dict[str, Any]],
        label_key: str,
        values_key: str,
        category_axis_label: str = "",
        value_axis_label: str = "",
        reverse: bool = False,
    ) -> dict[str, Any]:
        """Return chart data for labelled metric values."""
        if reverse:
            rows = list(reversed(rows))

        return {
            "labels": [row[label_key] for row in rows],
            "values": [row[values_key] for row in rows],
            "category_axis_label": category_axis_label,
            "value_axis_label": value_axis_label,
        }

    def _create_requests_chart_data(
        self,
        rows: list[dict[str, Any]],
        category_axis_label: str,
        *,
        horizontal: bool = False,
    ) -> dict[str, Any] | None:
        if not rows or any(row["requests"] is None for row in rows):
            return None
        data = self._create_chart_data(
            rows, "label", "requests", category_axis_label, "Requests", reverse=True
        )
        data["value_format"] = "count"
        if horizontal:
            data["horizontal"] = True
        return data

    def _build_key_usage(self, daily_results: list[dict[str, Any]]) -> dict[str, Any]:
        totals = self._breakdown_totals(daily_results, "api_keys")
        keys_by_alias = {
            key.litellm_alias: key for key in self._team.project.ai_gateway_keys.all()
        }
        rows = []
        for alias, metrics in totals.items():
            key = keys_by_alias.get(alias)
            url = (
                reverse(
                    "ai_gateway:key_detail", kwargs={"uuid": self._team.project.uuid, "pk": key.pk}
                )
                if key
                else None
            )
            rows.append(
                {
                    "id": alias,
                    "label": key.name if key else alias,
                    "url": url,
                    "spend": round(metrics["spend"], 2),
                    "requests": metrics["requests"],
                }
            )
        rows.sort(key=lambda row: row["spend"], reverse=True)
        chart_data = self._create_chart_data(
            rows, "label", "spend", "API Key", "Spend ($)", reverse=True
        )
        return {
            "has_usage": True,
            "rows": rows,
            "chart_data": chart_data,
            "chart_name": "key-spend",
            "chart_label": "Spend per API key",
            "requests_chart_data": self._create_requests_chart_data(rows, "API Key"),
            "requests_chart_name": "key-requests",
            "requests_chart_label": "Requests per API key",
        }

    def _build_model_usage(self, daily_results: list[dict[str, Any]]) -> dict[str, Any]:
        totals = self._breakdown_totals(daily_results, "model_groups")
        rows = [
            {
                "id": model_name,
                "label": model_name,
                "spend": round(metrics["spend"], 2),
                "requests": metrics["requests"],
                "input_tokens": metrics.get("input_tokens"),
                "output_tokens": metrics.get("output_tokens"),
            }
            for model_name, metrics in totals.items()
        ]
        rows.sort(key=lambda row: row["spend"], reverse=True)
        chart_data = self._create_chart_data(
            rows, "label", "spend", "Model", "Spend ($)", reverse=True
        )
        chart_data["horizontal"] = True
        return {
            "has_usage": True,
            "rows": rows,
            "chart_data": chart_data,
            "chart_name": "model-spend",
            "chart_label": "Spend per model",
            "requests_chart_data": self._create_requests_chart_data(
                rows, "Model", horizontal=True
            ),
            "requests_chart_name": "model-requests",
            "requests_chart_label": "Requests per model",
            "tokens_chart_data": self._create_tokens_chart_data(rows, "Model", horizontal=True),
            "tokens_chart_name": "model-tokens",
            "tokens_chart_label": "Input and output tokens per model",
        }

    @staticmethod
    def _accumulate_model_tokens(total: _UsageTotals, metrics: dict[str, Any]) -> None:
        input_tokens = metrics.get("prompt_tokens")
        output_tokens = metrics.get("completion_tokens")
        current_input = total.get("input_tokens", 0)
        current_output = total.get("output_tokens", 0)
        total["input_tokens"] = (
            None if input_tokens is None or current_input is None else current_input + input_tokens
        )
        total["output_tokens"] = (
            None
            if output_tokens is None or current_output is None
            else current_output + output_tokens
        )

    @staticmethod
    def _create_tokens_chart_data(
        rows: list[dict[str, Any]], category_axis_label: str, *, horizontal: bool = False
    ) -> dict[str, Any] | None:
        if not rows or any(
            row.get("input_tokens") is None or row.get("output_tokens") is None for row in rows
        ):
            return None
        ordered_rows = list(reversed(rows))
        return {
            "labels": [row["label"] for row in ordered_rows],
            "series": [
                {"name": "Input tokens", "values": [row["input_tokens"] for row in ordered_rows]},
                {
                    "name": "Output tokens",
                    "values": [row["output_tokens"] for row in ordered_rows],
                },
            ],
            "category_axis_label": category_axis_label,
            "value_axis_label": "Tokens",
            "value_format": "count",
            "horizontal": horizontal,
        }

    def _build_daily_usage(
        self,
        daily_results: list[dict[str, Any]],
        dimension: str,
        monthly_rows: list[dict[str, Any]],
        selected: str,
        month: date,
    ) -> dict[str, Any]:
        choices = [
            (row["id"], row["label"])
            for row in sorted(monthly_rows, key=lambda row: row["label"].casefold())
        ]
        labels = dict(choices)
        selected = selected if selected in labels else ""
        data: dict[str, Any] = {
            "choices": choices,
            "selected": selected,
            "label": labels.get(selected, ""),
            "rows": [],
        }
        if not selected:
            return data

        totals: dict[date, _UsageTotals] = {}
        for entry in daily_results:
            if not entry.get("date"):
                continue
            day = datetime.strptime(entry["date"], "%Y-%m-%d").date()
            if day.replace(day=1) != month:
                continue
            for item_id, item_data in entry.get("breakdown", {}).get(dimension, {}).items():
                identity = (
                    item_data.get("metadata", {}).get("key_alias")
                    if dimension == "api_keys"
                    else item_id
                )
                if identity != selected:
                    continue
                spend, requests = self._get_totals(item_data)
                total = totals.setdefault(day, {"spend": 0, "requests": 0})
                total["spend"] += spend
                if item_data.get("metrics", {}).get("api_requests") is None:
                    total["requests"] = None
                elif total["requests"] is not None:
                    total["requests"] += requests
                if dimension == "model_groups":
                    self._accumulate_model_tokens(total, item_data.get("metrics", {}))

        rows = [
            {"date": day, "label": day.strftime("%-d %B %Y"), **metrics}
            for day, metrics in sorted(totals.items(), reverse=True)
        ]
        chart_rows = [{**row, "label": row["date"].strftime("%-d")} for row in rows]
        axis_label = f"Day ({month.strftime('%B %Y')})"
        chart_data = self._create_chart_data(
            chart_rows, "label", "spend", axis_label, "Spend ($)", reverse=True
        )
        requests_chart_data = self._create_requests_chart_data(chart_rows, axis_label)
        if len(rows) > LINE_CHART_MIN_POINTS:
            chart_data["chart_type"] = "line"
            if requests_chart_data:
                requests_chart_data["chart_type"] = "line"
        prefix = "key" if dimension == "api_keys" else "model"
        description = f"{data['label']} in {month.strftime('%B %Y')}"
        data.update(
            {
                "rows": rows,
                "chart_data": chart_data,
                "chart_name": f"{prefix}-daily-spend",
                "chart_label": f"Daily spend for {description}",
                "requests_chart_data": requests_chart_data,
                "requests_chart_name": f"{prefix}-daily-requests",
                "requests_chart_label": f"Daily requests for {description}",
            }
        )
        if dimension == "model_groups":
            tokens_chart_data = self._create_tokens_chart_data(chart_rows, axis_label)
            if tokens_chart_data:
                tokens_chart_data["chart_type"] = chart_data.get("chart_type", "bar")
            data.update(
                {
                    "tokens_chart_data": tokens_chart_data,
                    "tokens_chart_name": "model-daily-tokens",
                    "tokens_chart_label": f"Daily input and output tokens for {description}",
                }
            )
        return data

    def _team_daily_activity(self, start: date, end: date) -> list[dict[str, Any]]:
        data = self._client.team_daily_activity(
            self._team.litellm_team_id, start.isoformat(), end.isoformat()
        )
        return data.get("results", [])

    def _get_totals(self, entry: dict[str, Any]) -> tuple[float, int]:
        metrics = entry.get("metrics", {})
        spend = metrics.get("spend", 0) or 0
        daily_requests = metrics.get("api_requests", 0) or 0
        return spend, daily_requests

    def _daily_rows(self, daily_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        totals = []
        for entry in daily_results:
            entry_date = entry.get("date")
            if not entry_date:
                continue
            spend, daily_requests = self._get_totals(entry)
            day = datetime.strptime(entry_date, "%Y-%m-%d").date()
            totals.append(
                {
                    "date": day,
                    "spend": spend,
                    "requests": daily_requests,
                    "label": day.strftime("%-d %B %Y"),
                }
            )
        totals.sort(key=lambda row: row["date"], reverse=True)
        return totals

    def _monthly_rows(self, daily_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Totals up a range of daily spends into totals for each month
        """
        spend_totals: dict[date, float] = {}
        request_totals: dict[date, int] = {}
        for entry in daily_results:
            entry_date = entry.get("date")
            if not entry_date:
                continue
            month = datetime.strptime(entry_date, "%Y-%m-%d").date().replace(day=1)
            spend, daily_requests = self._get_totals(entry)
            spend_totals[month] = spend_totals.get(month, 0) + spend
            request_totals[month] = request_totals.get(month, 0) + daily_requests

        return [
            {
                "label": month.strftime("%B %Y"),
                "spend": round(spend_totals[month], 2),
                "requests": request_totals[month],
            }
            for month in sorted(spend_totals, reverse=True)
        ]

    def _breakdown_totals(
        self, daily_results: list[dict[str, Any]], dimension: str
    ) -> dict[str, _UsageTotals]:
        totals: dict[str, _UsageTotals] = {}
        for entry in daily_results:
            for item_id, item_data in entry.get("breakdown", {}).get(dimension, {}).items():
                spend, daily_requests = self._get_totals(item_data)
                _id = item_id
                # API key ID/token changes when regenerated so use the alias to group spend by key
                if dimension == "api_keys":
                    _id = item_data["metadata"]["key_alias"]
                total = totals.setdefault(_id, {"spend": 0, "requests": 0})
                total["spend"] += spend
                if item_data.get("metrics", {}).get("api_requests") is None:
                    total["requests"] = None
                elif total["requests"] is not None:
                    total["requests"] += daily_requests
                if dimension == "model_groups":
                    self._accumulate_model_tokens(total, item_data.get("metrics", {}))

        return {
            item_id: total for item_id, total in totals.items() if round(total["spend"], 2) != 0
        }


class KeyService:
    """Coordinates AI Gateway key operations for a project.

    Holds an ``AIGatewayClient`` so related operations share one client and a
    single lifecycle. Use as a context manager to close the client on exit::

        with KeyService.from_settings() as service:
            service.create_key(project, name, models, created_by)
    """

    NO_DEFAULT_MODELS = "no-default-models"

    def __init__(self, client: AIGatewayClient) -> None:
        self._client = client

    @classmethod
    def from_settings(cls) -> KeyService:
        """Build a service backed by a client configured from Django settings."""
        return cls(AIGatewayClient.from_settings())

    def __enter__(self) -> KeyService:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying gateway client."""
        self._client.close()

    def list_available_models(self, project: Project) -> list[dict[str, Any]]:
        """Return the models ``project`` may select when creating a key.

        The models granted to the project's gateway team through its access
        groups. Before the team exists (the first key), the default access
        group's models are shown.
        """
        allowed = self._allowed_model_names(project)
        models = [
            self._enrich_model(model)
            for model in self._client.list_models_v1_info()
            if model.get("model_name") in allowed
        ]
        models.sort(key=lambda model: model["display_name"].lower())
        return models

    def list_public_models(self) -> list[dict[str, Any]]:
        """Returns models that are publicly available/can be requested"""
        return exclude_catalogue_models(
            self.list_all_models(), settings.AI_GATEWAY_CATALOGUE_EXCLUSIONS
        )

    def list_all_models(self) -> list[dict[str, Any]]:
        """Return every model on the gateway, regardless of project access.

        The app-level cost estimator is not scoped to a project, so it shows
        the same gateway model catalogue to every authenticated user.
        """
        models = [self._enrich_model(model) for model in self._client.list_models_v1_info()]
        models.sort(key=lambda model: model["display_name"].lower())
        return models

    def _allowed_model_names(self, project: Project) -> set[str]:
        """Return every model name ``project`` may currently use.

        Read from the project's gateway team access groups. Before the team
        exists (the first key), fall back to the default access group's models.
        """
        try:
            team = project.ai_gateway_team
        except Team.DoesNotExist:
            default_group = self._default_access_group_name()
            return set(self._client.list_models_for_access_group(default_group))

        data = self._client.team_info(team.litellm_team_id)
        return set(data.get("team_info", {}).get("access_group_models") or [])

    def _enrich_model(self, model: dict[str, Any]) -> dict[str, Any]:
        """Return a copy of ``model`` with display, pricing, and catalogue fields added."""
        model = model.copy()
        litellm_params = model.get("litellm_params", {})
        model_info = model.get("model_info", {})

        input_cost = model_info.get("input_cost_per_token")
        output_cost = model_info.get("output_cost_per_token")
        uplift_multiplier = model_info.get("regional_endpoint_uplift_multiplier")
        if uplift_multiplier is None:
            uplift_multiplier = 1

        model["input_cost_per_million"] = (
            input_cost * uplift_multiplier * 1_000_000 if input_cost is not None else None
        )
        model["output_cost_per_million"] = (
            output_cost * uplift_multiplier * 1_000_000 if output_cost is not None else None
        )
        model["display_name"] = litellm_params.get("ai_model_name") or model.get("model_name")
        model["provider"] = litellm_params.get("ai_model_provider")
        model["family"] = litellm_params.get("ai_model_family")
        model["generally_available"] = litellm_params.get("ai_model_generally_available")
        model["region"] = litellm_params.get("ai_model_location") or "Not specified"

        return model

    def create_key(
        self, project: Project, name: str, models: list[str], created_by: User
    ) -> tuple[str, int]:
        """Generate a gateway key for ``project`` and persist its metadata.

        Lazily creates the project's gateway team, calls the gateway to generate
        a key, then stores metadata and an encrypted copy of the secret. ``name``
        is the user-facing name (unique per project); a globally unique ``litellm_alias`` is
        derived from it for the gateway. Returns the plaintext key, which is shown to the user
        once.
        """
        team = self._get_or_create_team(project)
        litellm_alias = self._build_alias(project, name)
        logger.debug(
            "creating_key",
            project_id=project.pk,
            key_alias=litellm_alias,
        )
        data = self._client.generate_key(
            team.litellm_team_id,
            user_id=str(created_by.oid),
            key_alias=litellm_alias,
            models=models,
        )

        plaintext_key = data["key"]
        key = Key.objects.create(
            project=project,
            name=name,
            litellm_alias=litellm_alias,
            litellm_secret=plaintext_key,
            litellm_token=data.get("token", ""),
            masked_key=self._mask_key(plaintext_key),
            models=models,
            created_by=created_by,
        )
        return plaintext_key, key.pk

    def regenerate_key(self, key: Key) -> str:
        """Regenerate a gateway key for ``key`` and persist its metadata."""

        # Avoid holding a DB row lock while making a network call to the gateway.
        old_token_id = Key.objects.values_list("litellm_token", flat=True).get(pk=key.pk)
        logger.debug("regenerating_key", key_id=key.pk)
        data = self._client.regenerate_key(old_token_id)
        new_token_id = data["token_id"]
        new_key = data["key"]

        with transaction.atomic():
            db_key = Key.objects.select_for_update().get(pk=key.pk)
            db_key.litellm_secret = new_key
            db_key.litellm_token = new_token_id
            db_key.masked_key = self._mask_key(new_key)
            db_key.save(
                update_fields=["litellm_secret", "litellm_token", "masked_key", "modified"]
            )

        return new_key

    def bulk_delete_keys(self, keys: list[str]) -> None:
        """Bulk delete gateway keys identified by their secrets."""
        if keys:
            self._client.bulk_delete_keys(keys)

    def delete_team(self, team_id: str) -> None:
        """Delete the gateway team identified by ``team_id``."""
        logger.debug("delete_team", team_id=team_id)
        self._client.delete_team(team_id)

    def get_models_for_key(self, key: Key) -> list[str]:
        """Return model names for ``key``, using a short-lived cache.

        Cached entries are keyed by ``key.pk`` and ``key.modified`` so local
        key updates immediately shift lookups to a new cache key. A timeout is
        still applied to refresh data that may change remotely on the gateway.
        """
        cache_key = self._key_models_cache_key(key)
        cached_models = cache.get(cache_key)
        if cached_models is not None:
            return cached_models

        data = self._client.key_info(key.litellm_secret)
        models = data.get("info", {}).get("models", [])
        cache.set(cache_key, models, timeout=self._key_models_cache_timeout())
        return models

    def update_models_for_key(
        self,
        key: Key,
        models: list[str],
        changed_by: User | None = None,
    ) -> None:
        """Replace the models the gateway key ``key`` can call.

        Saves the last successfully applied model state so Simple History
        records the change and actor.
        """
        logger.debug("update_models_for_key", key_id=key.pk, models=models)
        self._client.update_key_models(key.litellm_token, models)
        self._record_applied_models(
            key,
            models,
            changed_by=changed_by,
            reason="Models changed",
        )

    def delete_key(self, key: Key) -> None:
        """Delete the virtual key from the gateway and remove its metadata."""
        logger.debug(
            "deleting_key",
            key_id=key.pk,
            key_alias=key.litellm_alias,
        )
        self._client.delete_key(key.litellm_token)
        key.delete()

    def reconcile_team_keys_to_allowed_models(
        self,
        team: Team,
        changed_by: User | None = None,
    ) -> tuple[list[str], list[str]]:
        """Reconcile each of ``team``'s keys to the models it may currently use.

        Reconciles every key against the team's allowed models, removing any
        model no longer permitted. A key left with no permitted models is given
        a sentinel so it cannot fall back to calling every model. Best-effort: a
        per-key gateway failure is recorded and reconciliation continues.

        Returns the ``(updated, failed)`` key aliases.
        """
        allowed = self._allowed_model_names(team.project)
        keys_by_alias = {
            key.litellm_alias: key
            for key in Key.objects.filter(project=team.project).select_related("project")
        }
        updated = []
        failed = []
        for gateway_key in self._client.list_team_keys(team.litellm_team_id):
            current = gateway_key.get("models", [])
            pruned = [model for model in current if model in allowed]
            if pruned == current:
                continue

            alias = gateway_key.get("key_alias", "")
            new_models = pruned or [self.NO_DEFAULT_MODELS]
            try:
                token = gateway_key.get("token", "")
                self._client.update_key_models(token, new_models)
            except AIGatewayError as error:
                sentry_sdk.capture_exception(error)
                failed.append(alias)
                continue

            if key := keys_by_alias.get(alias):
                self._record_applied_models(
                    key,
                    new_models,
                    changed_by=changed_by,
                    reason="Models reconciled after access group change",
                )
            updated.append(alias)

        return updated, failed

    def list_access_groups(self) -> list[dict[str, Any]]:
        """Return all access groups configured on the gateway."""
        return self._client.list_access_groups()

    def get_team_access_group_ids(self, team: Team) -> list[str]:
        """Return the ids of the access groups currently assigned to ``team``."""
        return self._client.get_team_access_group_ids(team.litellm_team_id)

    def _is_team_logging_required(self, access_group_ids: list[str]) -> bool:
        """Determine if logging is required based on access group IDs."""
        try:
            open_ai_access_group_id = self._client.get_access_group_id(
                settings.AI_GATEWAY_OPEN_AI_ACCESS_GROUP_NAME
            )
        except AIGatewayAPIError as error:
            if error.status_code != 404:
                raise
            open_ai_access_group_id = None

        return open_ai_access_group_id in access_group_ids

    def _is_team_logging_enabled(self, team: Team) -> bool:
        callbacks = self.get_team_callbacks(team)
        return "s3_v2" in callbacks["success_callbacks"]

    def enable_team_logging(self, team: Team) -> None:
        if self._is_team_logging_enabled(team):
            return
        self._client.enable_team_logging(team_id=team.litellm_team_id)

    def disable_team_logging(self, team: Team) -> None:
        if not self._is_team_logging_enabled(team):
            return
        self._client.disable_team_logging(team_id=team.litellm_team_id)

    def set_team_model_access(
        self,
        team: Team,
        access_group_ids: list[str],
        changed_by: User | None = None,
    ) -> tuple[list[str], list[str]]:
        """Replace the access groups assigned to ``team``, enable team logging if required, and
        reconcile all team keys.

        Changing a team's access groups can shrink the models it may use, so
        every key is reconciled with the new allowed set to keep keys from calling
        models the team no longer has.

        Returns the ``(updated, failed)`` key
        aliases from that reconciliation.
        """
        logging_required = self._is_team_logging_required(access_group_ids)
        # do this first, to avoid OpenAI access groups being enabled and enabling logging fails
        if logging_required:
            self.enable_team_logging(team=team)

        self._client.update_team_access_groups(team.litellm_team_id, access_group_ids)

        # do this after updating access groups, to avoid disabling logging prematurely
        if not logging_required:
            self.disable_team_logging(team=team)

        return self.reconcile_team_keys_to_allowed_models(team, changed_by=changed_by)

    def get_team_callbacks(self, team: Team) -> list[dict[str, Any]]:
        """Return the callbacks configured for the given team."""
        response = self._client.get_team_callbacks(team.litellm_team_id)
        return response.get("data", [])

    @cached_property
    def models_indexed_by_id(self) -> dict[str, dict[str, Any]]:
        """Return models keyed by their ID."""
        models = {}
        for model_info in self._client.list_models_v1_info():
            model_name = model_info.get("model_name")
            models[model_name] = model_info
        return models

    @staticmethod
    def _record_applied_models(
        key: Key,
        models: list[str],
        *,
        changed_by: User | None,
        reason: str,
    ) -> None:
        key.models = models
        key._history_user = changed_by
        key._change_reason = reason
        key.save(update_fields=["models", "modified"])

    @staticmethod
    def _key_models_cache_key(key: Key) -> str:
        """Return a versioned cache key for model names associated with ``key``."""
        return f"ai_gateway:key-models:{key.pk}:{key.modified.isoformat()}"

    @staticmethod
    def _key_models_cache_timeout() -> int:
        """Return model-cache timeout in seconds from settings or default."""
        return int(getattr(settings, "AI_GATEWAY_KEY_MODELS_CACHE_TIMEOUT", 300))

    def _get_or_create_team(self, project: Project) -> Team:
        """Return the project's gateway team, creating it on the gateway if needed."""
        try:
            return project.ai_gateway_team
        except Team.DoesNotExist:
            logger.debug("creating_new_team", project_id=str(project.uuid))
            access_group_id = self._client.get_access_group_id(self._default_access_group_name())
            team_id = self._client.create_team(str(project.uuid), [access_group_id])
            return Team.objects.create(project=project, litellm_team_id=team_id)

    @staticmethod
    def _default_access_group_name() -> str:
        """Return configured default access group name or raise if missing."""
        name = settings.DEFAULT_ACCESS_GROUP_NAME
        if not name:
            raise ImproperlyConfigured("DEFAULT_ACCESS_GROUP_NAME is not configured")
        return name

    @staticmethod
    def _build_alias(project: Project, name: str) -> str:
        """Build a globally unique, readable gateway alias from a project and name."""
        return f"{project.uuid}-{slugify(name)}-{secrets.token_hex(6)}"

    @staticmethod
    def _mask_key(key: str) -> str:
        """Return a display-safe fingerprint of a key, never the full secret."""
        if len(key) <= 4:
            return "..."
        return f"...{key[-4:]}"
