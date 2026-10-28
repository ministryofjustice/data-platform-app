from datetime import date
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone
from freezegun import freeze_time
from model_bakery import baker
from notifications_python_client.errors import HTTPError

from ai_gateway.exceptions import AIGatewayAPIError
from ai_gateway.services import record_budget_alert
from projects.models import ProjectPermission


@freeze_time("2026-10-28 05:00:00")
class TestCheckTeamSpend:
    def test_records_highest_warning_without_duplicates_or_sending(
        self, project, project_owner, notify_client
    ):
        team = baker.make("ai_gateway.Team", project=project)
        with patch(
            "ai_gateway.management.commands.check_team_spend.UsageService.from_settings"
        ) as factory:
            service = factory.return_value.__enter__.return_value
            service.get_budget_usage.return_value = (Decimal("460"), Decimal("500"))

            call_command("check_team_spend")
            call_command("check_team_spend")

        factory.assert_called_with(team=team)
        service.get_budget_usage.assert_called_with(month=date(2026, 10, 1))
        alert = project.budget_alerts.get()
        assert alert.threshold_percent == 90
        assert alert.notifications.get().sent_at is None
        notify_client.send_email_notification.assert_not_called()

    @pytest.mark.parametrize("budget", [Decimal("500"), None])
    def test_no_alert_below_threshold_or_without_budget(self, project, budget):
        baker.make("ai_gateway.Team", project=project)
        with patch(
            "ai_gateway.management.commands.check_team_spend.UsageService.from_settings"
        ) as factory:
            factory.return_value.__enter__.return_value.get_budget_usage.return_value = (
                Decimal("100"),
                budget,
            )

            call_command("check_team_spend")

        assert not project.budget_alerts.exists()

    def test_gateway_failure_does_not_stop_other_teams(self, project, project_owner):
        baker.make("ai_gateway.Team")
        baker.make("ai_gateway.Team", project=project)
        errors = StringIO()
        with patch(
            "ai_gateway.management.commands.check_team_spend.UsageService.from_settings"
        ) as factory:
            factory.return_value.__enter__.return_value.get_budget_usage.side_effect = [
                AIGatewayAPIError(500, "Gateway unavailable"),
                (Decimal("260"), Decimal("500")),
            ]

            with (
                patch(
                    "ai_gateway.management.commands.check_team_spend.sentry_sdk.capture_exception"
                ) as capture_exception,
                pytest.raises(CommandError, match="Failed 1"),
            ):
                call_command("check_team_spend", stderr=errors)

        capture_exception.assert_called_once()
        assert "Gateway unavailable" in str(capture_exception.call_args.args[0])
        assert "Gateway unavailable" in errors.getvalue()
        assert project.budget_alerts.get().notifications.get().sent_at is None

    def test_recorded_notification_is_sent_by_sending_command(
        self, project, project_owner, notify_client
    ):
        baker.make("ai_gateway.Team", project=project)
        with patch(
            "ai_gateway.management.commands.check_team_spend.UsageService.from_settings"
        ) as factory:
            factory.return_value.__enter__.return_value.get_budget_usage.return_value = (
                Decimal("260"),
                Decimal("500"),
            )

            call_command("check_team_spend")

        notification = project.budget_alerts.get().notifications.get()
        assert notification.sent_at is None

        call_command("send_budget_alerts")

        notification.refresh_from_db()
        assert notification.sent_at == timezone.now()
        notify_client.send_email_notification.assert_called_once()


@freeze_time("2026-10-28 05:00:00")
class TestSendBudgetAlerts:
    def test_selects_highest_alert_before_filtering_unsent_notifications(
        self, project, project_owner, notify_client
    ):
        lower = record_budget_alert(
            project=project, threshold=50, spend=Decimal("250"), budget=Decimal("500")
        )
        higher = record_budget_alert(
            project=project, threshold=90, spend=Decimal("450"), budget=Decimal("500")
        )

        call_command("send_budget_alerts")
        call_command("send_budget_alerts")

        assert lower.notifications.get().sent_at is None
        assert higher.notifications.get().sent_at == timezone.now()
        notify_client.send_email_notification.assert_called_once()

    def test_retries_alerts_for_each_budget_amount(self, project, project_owner, notify_client):
        original = record_budget_alert(
            project=project, threshold=90, spend=Decimal("450"), budget=Decimal("500")
        )
        increased = record_budget_alert(
            project=project, threshold=50, spend=Decimal("450"), budget=Decimal("800")
        )

        call_command("send_budget_alerts")

        assert original.notifications.get().sent_at == timezone.now()
        assert increased.notifications.get().sent_at == timezone.now()
        assert notify_client.send_email_notification.call_count == 2

    def test_failure_does_not_stop_other_recipients(
        self, project, project_owner, project_member, grant_project_permission, notify_client
    ):
        grant_project_permission(
            project=project, user=project_member, perm=ProjectPermission.MANAGE_API_KEYS
        )
        alert = record_budget_alert(
            project=project, threshold=50, spend=Decimal("250"), budget=Decimal("500")
        )
        notify_client.send_email_notification.side_effect = [
            HTTPError(message="Notify unavailable"),
            {"id": "11111111-1111-1111-1111-111111111111"},
        ]
        errors = StringIO()

        with (
            patch(
                "ai_gateway.management.commands.send_budget_alerts.sentry_sdk.capture_exception"
            ) as capture_exception,
            pytest.raises(CommandError, match="Failed to send 1"),
        ):
            call_command("send_budget_alerts", stderr=errors)

        capture_exception.assert_called_once()
        assert "Notify unavailable" in str(capture_exception.call_args.args[0])
        assert alert.notifications.filter(sent_at__isnull=True).count() == 1
        assert alert.notifications.filter(sent_at__isnull=False).count() == 1
        assert "Notify unavailable" in errors.getvalue()

        notify_client.send_email_notification.side_effect = None
        call_command("send_budget_alerts")

        assert not alert.notifications.filter(sent_at__isnull=True).exists()
        assert notify_client.send_email_notification.call_count == 3
