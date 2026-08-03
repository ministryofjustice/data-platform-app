"""Shared infrastructure services used across apps."""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from notifications_python_client.errors import HTTPError
from notifications_python_client.notifications import NotificationsAPIClient


class GovUKNotificationError(Exception):
    """Raised when GOV.UK Notify cannot send a notification."""


class GovUKNotificationsService:
    """General GOV.UK Notify adapter for sending messages."""

    def __init__(self, *, client: NotificationsAPIClient) -> None:
        self._client = client

    @classmethod
    def from_settings(cls) -> GovUKNotificationsService:
        """Build a generic Notify service from Django settings."""
        api_key = settings.NOTIFY_API_KEY
        if not api_key:
            raise ImproperlyConfigured("Missing Notify settings: NOTIFY_API_KEY")

        return cls(client=NotificationsAPIClient(api_key))

    def send_email(
        self,
        *,
        email_address: str,
        template_id: str,
        personalisation: dict[str, str],
    ) -> None:
        """Send an email via GOV.UK Notify and normalise transport errors."""
        try:
            self._client.send_email_notification(
                email_address=email_address,
                template_id=template_id,
                personalisation=personalisation,
            )
        except HTTPError as error:
            raise GovUKNotificationError(str(error)) from error
