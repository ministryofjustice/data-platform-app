from datetime import date
from decimal import Decimal
from unittest.mock import Mock, patch

import pytest
from model_bakery import baker
from notifications_python_client.notifications import NotificationsAPIClient

from data_platform_app.services import GovUKNotificationsService


@pytest.fixture
def key(db, project, user):
    """An existing AI Gateway key belonging to ``project``."""
    return baker.make(
        "ai_gateway.Key",
        project=project,
        name="primary-key",
        litellm_secret="sk-full-secret",
        masked_key="sk-abc...secret",
        created_by=user,
        models=["gpt-4"],
    )


@pytest.fixture
def budget_alert_notification(project, project_owner):
    alert = baker.make(
        "ai_gateway.BudgetAlert",
        project=project,
        period_start=date(2026, 10, 1),
        threshold_percent=50,
        spend=Decimal("250"),
        budget=Decimal("500"),
    )
    return baker.make(
        "ai_gateway.BudgetAlertNotification",
        alert=alert,
        recipient=project_owner,
        email_address=project_owner.email,
    )


@pytest.fixture
def notify_client(settings):
    settings.NOTIFY_BUDGET_ALERT_TEMPLATE_ID = "budget-alert-template"
    client = Mock(spec=NotificationsAPIClient)
    client.send_email_notification.return_value = {"id": "11111111-1111-1111-1111-111111111111"}
    with patch(
        "ai_gateway.services.GovUKNotificationsService.from_settings",
        return_value=GovUKNotificationsService(client=client),
    ):
        yield client
