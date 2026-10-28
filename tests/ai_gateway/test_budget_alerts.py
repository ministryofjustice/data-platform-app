from datetime import date
from decimal import Decimal

import pytest
from freezegun import freeze_time

from ai_gateway.services import budget_alert_threshold, record_budget_alert
from projects.models import ProjectPermission


class TestBudgetAlertThreshold:
    @pytest.mark.parametrize(
        ("spend", "expected"),
        [("49.999", None), ("50", 50), ("89.999", 50), ("90", 90), ("110", 90)],
    )
    def test_uses_unrounded_spend(self, spend, expected):
        assert budget_alert_threshold(spend=Decimal(spend), budget=Decimal("100")) == expected

    @pytest.mark.parametrize("budget", [None, Decimal("0")])
    def test_no_alert_without_a_budget(self, budget):
        assert budget_alert_threshold(spend=Decimal("100"), budget=budget) is None


@freeze_time("2026-10-28 05:00:00")
class TestRecordBudgetAlert:
    def test_new_members_not_added_to_existing_alert(
        self, project_owner, project, project_member, grant_project_permission
    ):
        alert = record_budget_alert(
            project=project, threshold=50, spend=Decimal("250"), budget=Decimal("500")
        )
        grant_project_permission(
            project=project, user=project_member, perm=ProjectPermission.MANAGE_API_KEYS
        )

        repeated = record_budget_alert(
            project=project, threshold=50, spend=Decimal("300"), budget=Decimal("500")
        )

        assert repeated is None
        assert project.budget_alerts.count() == 1
        alert.refresh_from_db()
        assert alert.spend == Decimal("250")
        assert alert.budget == Decimal("500")
        assert list(alert.notifications.values_list("recipient_id", flat=True)) == [
            project_owner.pk
        ]

    def test_recording_90_percent_does_not_create_a_50_percent_alert(self, project, project_owner):
        alert = record_budget_alert(
            project=project,
            threshold=90,
            spend=Decimal("460"),
            budget=Decimal("500"),
        )

        assert alert.threshold_percent == 90
        assert project.budget_alerts.count() == 1
        assert list(alert.notifications.values_list("recipient_id", flat=True)) == [
            project_owner.pk
        ]

    def test_recording_90_percent_keeps_existing_50_percent_alert(self, project, project_owner):
        lower = record_budget_alert(
            project=project, threshold=50, spend=Decimal("250"), budget=Decimal("500")
        )

        higher = record_budget_alert(
            project=project, threshold=90, spend=Decimal("450"), budget=Decimal("500")
        )

        alerts = list(project.budget_alerts.all())
        assert len(alerts) == 2
        assert lower in alerts
        assert higher in alerts

    def test_lower_threshold_for_same_budget_is_not_recorded(self, project, project_owner):
        higher = record_budget_alert(
            project=project, threshold=90, spend=Decimal("460"), budget=Decimal("500")
        )

        lower = record_budget_alert(
            project=project, threshold=50, spend=Decimal("460"), budget=Decimal("500")
        )

        assert lower is None
        assert list(project.budget_alerts.all()) == [higher]

    @pytest.mark.parametrize(("threshold", "spend"), [(50, "460"), (90, "720")])
    def test_budget_increase_allows_new_alerts(self, project, project_owner, threshold, spend):
        original = record_budget_alert(
            project=project, threshold=90, spend=Decimal("460"), budget=Decimal("500")
        )

        increased = record_budget_alert(
            project=project, threshold=threshold, spend=Decimal(spend), budget=Decimal("800")
        )

        assert increased is not None
        assert increased.threshold_percent == threshold
        assert increased.budget == Decimal("800")
        assert increased.notifications.count() == 1
        alerts = list(project.budget_alerts.all())
        assert len(alerts) == 2
        assert original in alerts
        assert increased in alerts

    def test_new_month_creates_a_new_warning(self, project, project_owner):
        first = record_budget_alert(
            project=project, threshold=50, spend=Decimal("250"), budget=Decimal("500")
        )

        with freeze_time("2026-11-01 05:00:00"):
            second = record_budget_alert(
                project=project, threshold=50, spend=Decimal("250"), budget=Decimal("500")
            )

        assert first.pk != second.pk
        assert first.period_start == date(2026, 10, 1)
        assert second.period_start == date(2026, 11, 1)
        assert second.notifications.count() == 1

    def test_inactive_api_key_manager_has_no_notification_record(self, project, project_owner):
        project_owner.is_active = False
        project_owner.save()

        alert = record_budget_alert(
            project=project, threshold=50, spend=Decimal("250"), budget=Decimal("500")
        )

        assert not alert.notifications.exists()

    def test_member_without_api_key_permission_has_no_notification_record(
        self, project, project_member, grant_project_permission
    ):
        grant_project_permission(
            project=project,
            user=project_member,
            perm=ProjectPermission.MANAGE_MEMBERS,
        )

        alert = record_budget_alert(
            project=project, threshold=50, spend=Decimal("250"), budget=Decimal("500")
        )

        assert not alert.notifications.exists()
