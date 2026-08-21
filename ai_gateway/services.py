"""Service layer for AI Gateway key operations."""

from __future__ import annotations

import calendar
import secrets
from datetime import date, datetime
from typing import Any

import sentry_sdk
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.urls import reverse
from django.utils.text import slugify

from ai_gateway.client import AIGatewayClient
from ai_gateway.exceptions import AIGatewayError
from ai_gateway.models import Key, Team
from projects.models import Project
from users.models import User

MONTHS_IN_MONTH_PICKER = 12
MONTHS_OF_SPEND_HISTORY = 6
DAILY_SPEND_PREVIEW_COUNT = 10


def usage_month_choices(today: date | None = None) -> list[date]:
    """Return the most recent ``MONTHS_IN_MONTH_PICKER`` months, newest first.

    Each value is the first day of a calendar month, suitable for populating
    the usage page's month selector.
    """
    today = today or date.today()
    year, month = today.year, today.month
    months = []
    for _ in range(MONTHS_IN_MONTH_PICKER):
        months.append(date(year, month, 1))
        month -= 1
        if month == 0:
            month, year = 12, year - 1
    return months


def parse_usage_month(value: str | None, today: date | None = None) -> date:
    """Parse a ``YYYY-MM`` month value, falling back to the current month."""
    today = today or date.today()
    if value:
        try:
            parsed = datetime.strptime(value, "%Y-%m").date()
        except ValueError:
            return today.replace(day=1)
        if parsed in usage_month_choices(today):
            return parsed
    return today.replace(day=1)


def end_of_month(day: date) -> date:
    """Return the last calendar day of the month containing ``day``."""
    last_day = calendar.monthrange(day.year, day.month)[1]
    return day.replace(day=last_day)


def shift_months(day: date, months: int) -> date:
    """Return the first of the month ``months`` months away from ``day``."""
    month_index = day.year * 12 + (day.month - 1) + months
    year, month = divmod(month_index, 12)
    return date(year, month + 1, 1)


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
        return [
            self._enrich_model(model)
            for model in self._client.list_models_v1_info()
            if model.get("model_name") in allowed
        ]

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
        """Return a copy of ``model`` with display and pricing fields added."""
        model = model.copy()
        litellm_params = model.get("litellm_params", {})
        model_info = model.get("model_info", {})

        input_cost = model_info.get("input_cost_per_token")
        output_cost = model_info.get("output_cost_per_token")

        model["input_cost_per_million"] = (
            input_cost * 1_000_000 if input_cost is not None else None
        )
        model["output_cost_per_million"] = (
            output_cost * 1_000_000 if output_cost is not None else None
        )
        model["display_name"] = litellm_params.get("ai_model_name") or model.get("model_name")
        model["provider"] = litellm_params.get("ai_model_provider")
        model["family"] = litellm_params.get("ai_model_family")

        return model

    def create_key(self, project: Project, name: str, models: list[str], created_by: User) -> str:
        """Generate a gateway key for ``project`` and persist its metadata.

        Lazily creates the project's gateway team, calls the gateway to generate
        a key, then stores metadata and an encrypted copy of the secret. ``name``
        is the user-facing name (unique per project); a globally unique ``litellm_alias`` is
        derived from it for the gateway. Returns the plaintext key, which is shown to the user
        once.
        """
        team = self._get_or_create_team(project)
        litellm_alias = self._build_alias(project, name)
        data = self._client.generate_key(
            team.litellm_team_id, key_alias=litellm_alias, models=models
        )

        plaintext_key = data["key"]
        Key.objects.create(
            project=project,
            name=name,
            litellm_alias=litellm_alias,
            litellm_secret=plaintext_key,
            litellm_token=data.get("token", ""),
            masked_key=self._mask_key(plaintext_key),
            models=models,
            created_by=created_by,
        )
        return plaintext_key

    def regenerate_key(self, key: Key) -> str:
        """Regenerate a gateway key for ``key`` and persist its metadata."""

        # Avoid holding a DB row lock while making a network call to the gateway.
        old_token_id = Key.objects.values_list("litellm_token", flat=True).get(pk=key.pk)
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
        self._client.update_key_models(key.litellm_token, models)
        self._record_applied_models(
            key,
            models,
            changed_by=changed_by,
            reason="Models changed",
        )

    def delete_key(self, key: Key) -> None:
        """Delete the virtual key from the gateway and remove its metadata."""
        self._client.delete_key(key.litellm_token)
        key.delete()

    def get_usage_overview(self, project: Project, month: date) -> dict[str, Any]:
        """Return spend-overview data for ``project`` for the calendar month ``month``.

        Returns ``{"has_usage": False}`` when the project has never used the
        gateway. Otherwise includes the total spend and remaining budget for
        the month, a daily spend breakdown (as a table and a chart), and a
        trailing monthly summary, shaped ready for the usage templates.
        """
        team = self._get_existing_team(project)
        if team is None:
            return {"has_usage": False}

        month_start = month.replace(day=1)
        month_end = end_of_month(month)
        daily_results = self._team_daily_activity(team, month_start, month_end)
        daily_spend = self._daily_totals(daily_results)
        total_spend = round(sum(day["spend"] for day in daily_spend), 2)

        history_start = shift_months(month_start, -(MONTHS_OF_SPEND_HISTORY - 1))
        monthly_results = (
            daily_results
            if history_start == month_start
            else self._team_daily_activity(team, history_start, month_end)
        )
        monthly_spend = self._monthly_totals(monthly_results)

        max_budget = self._team_max_budget(team)
        budget_remaining = None if max_budget is None else round(max_budget - total_spend, 2)
        percent_used = None if not max_budget else round((total_spend / max_budget) * 100, 1)

        daily_rows = [
            {"label": day["date"].strftime("%-d %B %Y"), "spend": day["spend"]}
            for day in daily_spend
        ]
        monthly_rows = [
            {"label": month_row["month"].strftime("%B %Y"), "spend": month_row["spend"]}
            for month_row in monthly_spend
        ]

        daily_show_all = None
        if len(daily_rows) > DAILY_SPEND_PREVIEW_COUNT:
            daily_show_all = {
                "shown": DAILY_SPEND_PREVIEW_COUNT,
                "total": len(daily_rows),
                "url": f"?month={month_start.strftime('%Y-%m')}&daily=all",
            }

        return {
            "has_usage": True,
            "total_spend": total_spend,
            "max_budget": max_budget,
            "budget_remaining": budget_remaining,
            "percent_used": percent_used,
            "daily_spend": daily_rows,
            "daily_spend_preview": daily_rows[:DAILY_SPEND_PREVIEW_COUNT],
            "daily_show_all": daily_show_all,
            "daily_chart": None,
            "daily_chart_label": f"Daily spend for {month_start.strftime('%B %Y')}",
            "monthly_spend_rows": monthly_rows,
            "monthly_chart": None,
        }

    def get_usage_by_key(self, project: Project, month: date) -> dict[str, Any]:
        """Return per-API-key spend for ``project`` for the calendar month ``month``."""
        team = self._get_existing_team(project)
        if team is None:
            return {"has_usage": False}

        daily_results = self._team_daily_activity(team, month.replace(day=1), end_of_month(month))
        totals = self._breakdown_totals(daily_results, "api_keys")

        keys_by_token = {key.litellm_token: key for key in project.ai_gateway_keys.all()}
        rows = []
        for token, spend in totals.items():
            key = keys_by_token.get(token)
            url = (
                reverse("ai_gateway:key_detail", kwargs={"uuid": project.uuid, "pk": key.pk})
                if key
                else None
            )
            rows.append(
                {"label": key.name if key else token, "url": url, "spend": round(spend, 2)}
            )
        rows.sort(key=lambda row: row["spend"], reverse=True)

        return {
            "has_usage": True,
            "rows": rows,
            "chart": None,
            "chart_label": "Spend per API key",
        }

    def get_usage_by_model(self, project: Project, month: date) -> dict[str, Any]:
        """Return per-model spend for ``project`` for the calendar month ``month``."""
        team = self._get_existing_team(project)
        if team is None:
            return {"has_usage": False}

        daily_results = self._team_daily_activity(team, month.replace(day=1), end_of_month(month))
        totals = self._breakdown_totals(daily_results, "models")

        rows = [
            {"label": model_name, "spend": round(spend, 2)} for model_name, spend in totals.items()
        ]
        rows.sort(key=lambda row: row["spend"], reverse=True)

        return {"has_usage": True, "rows": rows, "chart": None, "chart_label": "Spend per model"}

    def _team_daily_activity(self, team: Team, start: date, end: date) -> list[dict[str, Any]]:
        """Return the raw ``results`` list from the gateway for a date range."""
        data = self._client.team_daily_activity(
            team.litellm_team_id,
            start.isoformat(),
            end.isoformat(),
        )
        return data.get("results", [])

    def _team_max_budget(self, team: Team) -> float | None:
        """Return the team's configured monthly budget, if the gateway reports one."""
        data = self._client.team_info(team.litellm_team_id)
        return data.get("team_info", {}).get("max_budget")

    @staticmethod
    def _daily_totals(daily_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Return ``[{"date": date, "spend": float}, ...]`` sorted most recent first."""
        totals = []
        for entry in daily_results:
            entry_date = entry.get("date")
            if not entry_date:
                continue
            spend = entry.get("metrics", {}).get("spend", 0) or 0
            totals.append(
                {"date": datetime.strptime(entry_date, "%Y-%m-%d").date(), "spend": spend}
            )
        totals.sort(key=lambda row: row["date"], reverse=True)
        return totals

    @staticmethod
    def _monthly_totals(daily_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Aggregate daily results into ``[{"month": date, "spend": float}, ...]``.

        Months are returned most recent first, as the first day of each month.
        """
        totals: dict[date, float] = {}
        for entry in daily_results:
            entry_date = entry.get("date")
            if not entry_date:
                continue
            day = datetime.strptime(entry_date, "%Y-%m-%d").date()
            month_key = day.replace(day=1)
            spend = entry.get("metrics", {}).get("spend", 0) or 0
            totals[month_key] = totals.get(month_key, 0) + spend
        return [
            {"month": month_key, "spend": round(spend, 2)}
            for month_key, spend in sorted(totals.items(), reverse=True)
        ]

    @staticmethod
    def _breakdown_totals(daily_results: list[dict[str, Any]], dimension: str) -> dict[str, float]:
        """Sum spend across all days for each entry in ``breakdown[dimension]``.

        ``dimension`` is ``"api_keys"`` or ``"models"``, matching the gateway's
        daily-activity breakdown structure. Returns a mapping of item id (the
        gateway token for api keys, or model name for models) to total spend.
        """
        totals: dict[str, float] = {}
        for entry in daily_results:
            breakdown = entry.get("breakdown", {}).get(dimension, {})
            for item_id, item_data in breakdown.items():
                spend = item_data.get("metrics", {}).get("spend", 0) or 0
                totals[item_id] = totals.get(item_id, 0) + spend
        return totals

    def _get_existing_team(self, project: Project) -> Team | None:
        """Return the project's gateway team, without creating one if missing."""
        try:
            return project.ai_gateway_team
        except Team.DoesNotExist:
            return None

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

    def set_team_model_access(
        self,
        team: Team,
        access_group_ids: list[str],
        changed_by: User | None = None,
    ) -> tuple[list[str], list[str]]:
        """Replace the access groups assigned to ``team`` and reconcile its keys.

        Changing a team's access groups can shrink the models it may use, so
        every key is reconciled with the new allowed set to keep keys from calling
        models the team no longer has. Returns the ``(updated, failed)`` key
        aliases from that reconciliation.
        """
        self._client.update_team_access_groups(team.litellm_team_id, access_group_ids)
        return self.reconcile_team_keys_to_allowed_models(team, changed_by=changed_by)

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
