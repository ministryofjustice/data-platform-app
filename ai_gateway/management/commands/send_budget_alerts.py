"""Send outstanding notifications for the highest monthly budget alerts."""

import sentry_sdk
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
        sent = 0
        for notification in notifications:
            if (
                not notification.alert.project.memberships.can_manage_api_keys()
                .filter(user_id=notification.recipient_id)
                .exists()
            ):
                continue

            try:
                send_budget_alert_notification(notification=notification)
                sent += 1
            except GovUKNotificationError as error:
                sentry_sdk.capture_exception(error)
                failed += 1
                self.stderr.write(
                    self.style.ERROR(f"Failed to send notification {notification.pk}: {error}")
                )

        self.stdout.write(
            f"""
            Finished sending budget notifications.
            Sent {sent} notification(s).
            Failed {failed} notification(s).
            """
        )
        if failed:
            raise CommandError(f"Failed to send {failed} budget notification(s).")
