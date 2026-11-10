"""Shared view mixins for AI Gateway pages."""

from datetime import date

import sentry_sdk
from django.utils import timezone

from ai_gateway.exceptions import AIGatewayError
from ai_gateway.models import Team
from ai_gateway.services import UsageService


class BudgetLimitBannerMixin:
    """Add current-month budget status to a project page's template context."""

    budget_limit_banner_auto = True

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.budget_limit_banner_auto:
            context["show_budget_limit_banner"] = self.get_budget_limit_banner()
        return context

    def get_budget_limit_banner(
        self,
        *,
        team: Team | None = None,
        service: UsageService | None = None,
        month: date | None = None,
    ) -> bool:
        """Return whether the project's current-month budget limit has been reached."""
        month = month or timezone.localdate()
        current_month = timezone.localdate().replace(day=1)
        if month.replace(day=1) != current_month:
            return False

        if team is None:
            project = getattr(self, "project", None)
            if project is None:
                obj = getattr(self, "object", None)
                project = getattr(obj, "project", obj)
            if project is None:
                return False
            try:
                team = project.ai_gateway_team
            except Team.DoesNotExist:
                return False

        try:
            if service is not None:
                return service.is_at_budget_limit(month)
            with UsageService.from_settings(team=team) as budget_service:
                return budget_service.is_at_budget_limit(month)
        except AIGatewayError as error:
            sentry_sdk.capture_exception(error)
            return False
