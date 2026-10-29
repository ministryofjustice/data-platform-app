"""Check monthly project spend and record newly reached budget warnings."""

import sentry_sdk
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from ai_gateway.exceptions import AIGatewayError
from ai_gateway.models import Team
from ai_gateway.services import (
    UsageService,
    budget_alert_threshold,
    record_budget_alert,
)


class Command(BaseCommand):
    help = "Check team spend and record newly reached budget warnings."

    def handle(self, *args, **options):
        month = timezone.localdate().replace(day=1)
        created = 0
        failed = 0
        for team in Team.objects.select_related("project").order_by("pk"):
            try:
                with UsageService.from_settings(team=team) as service:
                    spend, budget = service.get_budget_usage(month=month)
            except AIGatewayError as error:
                sentry_sdk.capture_exception(error)
                failed += 1
                self.stderr.write(self.style.ERROR(f"Failed to check team {team.pk}: {error}"))
                continue

            if budget is None:
                continue

            threshold = budget_alert_threshold(spend=spend, budget=budget)
            if threshold is None:
                continue

            alert = record_budget_alert(
                project=team.project, threshold=threshold, spend=spend, budget=budget
            )
            if alert is None:
                continue
            created += 1

        self.stdout.write(f"Created {created} budget alert(s); failed {failed} team check(s).")
        if failed:
            raise CommandError(f"Failed {failed} team budget check(s).")
