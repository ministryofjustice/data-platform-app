"""Service layer for project membership notifications."""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from data_platform_app.services import GovUKNotificationError, GovUKNotificationsService
from data_platform_app.utils import build_base_url


class ProjectNotificationError(Exception):
    """Raised when a project membership notification cannot be sent."""


class ProjectMembershipNotificationService:
    """Send project membership emails using GOV.UK Notify templates."""

    def __init__(
        self,
        *,
        notifications_service: GovUKNotificationsService,
        member_added_template_id: str,
        member_removed_template_id: str,
    ) -> None:
        self._notifications_service = notifications_service
        self._member_added_template_id = member_added_template_id
        self._member_removed_template_id = member_removed_template_id

    @classmethod
    def from_settings(cls) -> ProjectMembershipNotificationService:
        """Build a service backed by GOV.UK Notify settings."""
        member_added_template_id = settings.NOTIFY_PROJECT_MEMBER_ADDED_TEMPLATE_ID
        member_removed_template_id = settings.NOTIFY_PROJECT_MEMBER_REMOVED_TEMPLATE_ID

        missing = []
        if not member_added_template_id:
            missing.append("NOTIFY_PROJECT_MEMBER_ADDED_TEMPLATE_ID")
        if not member_removed_template_id:
            missing.append("NOTIFY_PROJECT_MEMBER_REMOVED_TEMPLATE_ID")

        if missing:
            missing_fields = ", ".join(missing)
            raise ImproperlyConfigured(f"Missing Notify settings: {missing_fields}")

        return cls(
            notifications_service=GovUKNotificationsService.from_settings(),
            member_added_template_id=member_added_template_id,
            member_removed_template_id=member_removed_template_id,
        )

    def send_member_added_email(self, *, project, member, added_by) -> None:
        """Send a member-added email to ``member`` for ``project``."""
        if not member.email:
            return

        try:
            project_url = f"{build_base_url(settings.APP_ENV)}{project.get_absolute_url()}"
            self._notifications_service.send_email(
                email_address=member.email,
                template_id=self._member_added_template_id,
                personalisation={
                    "project_name": project.name,
                    "project_description": project.description,
                    "added_by_email": added_by.email,
                    "project_url": project_url,
                },
            )
        except GovUKNotificationError as error:
            raise ProjectNotificationError(str(error)) from error

    def send_member_removed_email(self, *, project, member, removed_by) -> None:
        """Send a member-removed email to ``member`` for ``project``."""
        if not member.email:
            return

        try:
            self._notifications_service.send_email(
                email_address=member.email,
                template_id=self._member_removed_template_id,
                personalisation={
                    "project_name": project.name,
                    "remover_email": removed_by.email,
                },
            )
        except GovUKNotificationError as error:
            raise ProjectNotificationError(str(error)) from error
