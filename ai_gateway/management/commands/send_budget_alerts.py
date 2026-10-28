"""Send outstanding notifications for the highest monthly budget alerts."""

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from ai_gateway.models import BudgetAlert, BudgetAlertNotification
from ai_gateway.services import send_budget_alert_notification
from data_platform_app.services import GovUKNotificationError


class Command(BaseCommand):
    help = "Send pending notifications for the highest current-month budget alerts."

    def handle(self, *args, **options):
        # DISTINCT ON keeps the first (highest-threshold) alert for each project/budget.
        alerts = (
            BudgetAlert.objects.filter(period_start=timezone.localdate().replace(day=1))
            .order_by("project_id", "budget", "-threshold_percent")
            .distinct("project_id", "budget")
        )
        notifications = (
            BudgetAlertNotification.objects.pending().filter(alert__in=alerts).order_by("pk")
        )
        failed = 0
        for notification in notifications:
            try:
                send_budget_alert_notification(notification=notification)
            except GovUKNotificationError as error:
                failed += 1
                self.stderr.write(
                    self.style.ERROR(f"Failed to send notification {notification.pk}: {error}")
                )

        self.stdout.write(
            f"Finished sending budget notifications; failed {failed} notification(s)."
        )
        if failed:
            raise CommandError(f"Failed to send {failed} budget notification(s).")
