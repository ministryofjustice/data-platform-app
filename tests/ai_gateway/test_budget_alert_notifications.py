from uuid import UUID

import pytest
from django.utils import timezone
from freezegun import freeze_time
from notifications_python_client.errors import HTTPError

from ai_gateway.models import BudgetAlertNotification
from ai_gateway.services import send_budget_alert_notification
from data_platform_app.services import GovUKNotificationError


@freeze_time("2026-10-28 05:00:00")
class TestSendBudgetAlertNotification:
    @pytest.mark.parametrize("threshold", [50, 90])
    def test_sends_warning_and_records_notify_acceptance(
        self,
        budget_alert_notification,
        notify_client,
        threshold,
    ):
        alert = budget_alert_notification.alert
        alert.threshold_percent = threshold
        alert.save()

        send_budget_alert_notification(notification=budget_alert_notification)

        notify_client.send_email_notification.assert_called_once_with(
            email_address=budget_alert_notification.email_address,
            template_id="budget-alert-template",
            personalisation={
                "project_name": alert.project.name,
                "project_url": (
                    "https://test.data-platform.service.justice.gov.uk"
                    f"/app/projects/{alert.project.uuid}/ai-gateway/usage/"
                ),
                "threshold_percent": str(threshold),
            },
        )
        budget_alert_notification.refresh_from_db()
        assert budget_alert_notification.sent_at == timezone.now()
        assert budget_alert_notification.notify_notification_id == UUID(
            "11111111-1111-1111-1111-111111111111"
        )

    def test_repeated_send_does_not_resubmit_an_accepted_notification(
        self, budget_alert_notification, notify_client
    ):
        send_budget_alert_notification(notification=budget_alert_notification)
        send_budget_alert_notification(notification=budget_alert_notification)

        assert notify_client.send_email_notification.call_count == 1

    def test_failed_submission_remains_unsent_and_can_be_retried(
        self, budget_alert_notification, notify_client
    ):
        notify_client.send_email_notification.side_effect = HTTPError("Notify unavailable")

        with pytest.raises(GovUKNotificationError):
            send_budget_alert_notification(notification=budget_alert_notification)

        budget_alert_notification.refresh_from_db()
        assert budget_alert_notification.sent_at is None
        assert budget_alert_notification.notify_notification_id is None

        notify_client.send_email_notification.side_effect = None
        send_budget_alert_notification(notification=budget_alert_notification)

        budget_alert_notification.refresh_from_db()
        assert budget_alert_notification.sent_at == timezone.now()
        assert notify_client.send_email_notification.call_count == 2


@freeze_time("2026-10-28 05:00:00")
class TestPendingBudgetAlertNotifications:
    def test_eligible_unsent_warning_is_selected(self, budget_alert_notification):
        assert list(BudgetAlertNotification.objects.pending()) == [budget_alert_notification]

    def test_sent_warning_is_not_selected(self, budget_alert_notification):
        budget_alert_notification.sent_at = timezone.now()
        budget_alert_notification.save()

        assert not BudgetAlertNotification.objects.pending().exists()

    def test_previous_month_warning_is_not_selected(self, budget_alert_notification):
        with freeze_time("2026-11-01 05:00:00"):
            assert not BudgetAlertNotification.objects.pending().exists()
