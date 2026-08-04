from unittest.mock import Mock, patch

import pytest
from django.core.exceptions import ImproperlyConfigured
from model_bakery import baker
from notifications_python_client.errors import HTTPError

from data_platform_app.services import GovUKNotificationError, GovUKNotificationsService
from projects.services import (
    ProjectMembershipNotificationService,
    ProjectNotificationError,
)


class TestGovUKNotificationsService:
    def test_from_settings_builds_client(self, settings):
        settings.NOTIFY_API_KEY = "test-notify-api-key"

        with patch("data_platform_app.services.NotificationsAPIClient") as client_class:
            service = GovUKNotificationsService.from_settings()

        client_class.assert_called_once_with("test-notify-api-key")
        assert service._client is client_class.return_value

    def test_from_settings_raises_when_api_key_missing(self, settings):
        settings.NOTIFY_API_KEY = ""

        with pytest.raises(ImproperlyConfigured) as exc_info:
            GovUKNotificationsService.from_settings()

        assert "NOTIFY_API_KEY" in str(exc_info.value)

    def test_send_email_calls_notify(self):
        client = Mock()
        service = GovUKNotificationsService(client=client)

        service.send_email(
            email_address="person@example.com",
            template_id="template-id",
            personalisation={"project_name": "My Project"},
        )

        client.send_email_notification.assert_called_once_with(
            email_address="person@example.com",
            template_id="template-id",
            personalisation={"project_name": "My Project"},
        )

    def test_send_email_raises_normalised_error_on_http_failure(self):
        client = Mock()
        client.send_email_notification.side_effect = HTTPError(response=Mock())
        service = GovUKNotificationsService(client=client)

        with pytest.raises(GovUKNotificationError):
            service.send_email(
                email_address="person@example.com",
                template_id="template-id",
                personalisation={"project_name": "My Project"},
            )


class TestProjectMembershipNotificationService:
    def test_from_settings_builds_service(self, settings):
        settings.NOTIFY_PROJECT_MEMBER_ADDED_TEMPLATE_ID = "11111111-1111-1111-1111-111111111111"
        settings.NOTIFY_PROJECT_MEMBER_REMOVED_TEMPLATE_ID = "22222222-2222-2222-2222-222222222222"
        generic_service = Mock(spec=GovUKNotificationsService)

        with patch(
            "projects.services.GovUKNotificationsService.from_settings",
            return_value=generic_service,
        ) as from_settings:
            service = ProjectMembershipNotificationService.from_settings()

        from_settings.assert_called_once_with()
        assert service._notifications_service is generic_service

    def test_from_settings_raises_when_required_settings_missing(self, settings):
        settings.NOTIFY_API_KEY = ""
        settings.NOTIFY_PROJECT_MEMBER_ADDED_TEMPLATE_ID = ""
        settings.NOTIFY_PROJECT_MEMBER_REMOVED_TEMPLATE_ID = ""

        with pytest.raises(ImproperlyConfigured) as exc_info:
            ProjectMembershipNotificationService.from_settings()

        assert "NOTIFY_PROJECT_MEMBER_ADDED_TEMPLATE_ID" in str(exc_info.value)
        assert "NOTIFY_PROJECT_MEMBER_REMOVED_TEMPLATE_ID" in str(exc_info.value)

    @pytest.mark.django_db
    def test_send_member_added_email_calls_notify(self):
        notifications_service = Mock(spec=GovUKNotificationsService)
        project = baker.make("projects.Project", name="My Project")
        member = baker.make(
            "users.User",
            email="member.added@example.com",
            first_name="Member",
            last_name="Added",
        )
        actor = baker.make(
            "users.User",
            email="actor@example.com",
            first_name="Action",
            last_name="User",
        )
        service = ProjectMembershipNotificationService(
            notifications_service=notifications_service,
            member_added_template_id="11111111-1111-1111-1111-111111111111",
            member_removed_template_id="22222222-2222-2222-2222-222222222222",
        )

        service.send_member_added_email(project=project, member=member, added_by=actor)

        notifications_service.send_email.assert_called_once_with(
            email_address="member.added@example.com",
            template_id="11111111-1111-1111-1111-111111111111",
            personalisation={
                "project_name": "My Project",
                "project_description": project.description,
                "added_by_email": "actor@example.com",
                "project_url": f"https://test.data-platform.service.justice.gov.uk{project.get_absolute_url()}",
            },
        )

    @pytest.mark.django_db
    def test_send_member_removed_email_calls_notify(self):
        notifications_service = Mock(spec=GovUKNotificationsService)
        project = baker.make("projects.Project", name="My Project")
        member = baker.make(
            "users.User",
            email="member.removed@example.com",
            first_name="Member",
            last_name="Removed",
        )
        actor = baker.make(
            "users.User",
            email="actor@example.com",
            first_name="Action",
            last_name="User",
        )
        service = ProjectMembershipNotificationService(
            notifications_service=notifications_service,
            member_added_template_id="11111111-1111-1111-1111-111111111111",
            member_removed_template_id="22222222-2222-2222-2222-222222222222",
        )

        service.send_member_removed_email(project=project, member=member, removed_by=actor)

        notifications_service.send_email.assert_called_once_with(
            email_address="member.removed@example.com",
            template_id="22222222-2222-2222-2222-222222222222",
            personalisation={
                "project_name": "My Project",
                "remover_email": "actor@example.com",
            },
        )

    @pytest.mark.django_db
    def test_send_member_added_email_skips_users_without_email(self):
        notifications_service = Mock(spec=GovUKNotificationsService)
        project = baker.make("projects.Project", name="My Project")
        member = baker.make("users.User", email="")
        actor = baker.make("users.User", email="actor@example.com")
        service = ProjectMembershipNotificationService(
            notifications_service=notifications_service,
            member_added_template_id="11111111-1111-1111-1111-111111111111",
            member_removed_template_id="22222222-2222-2222-2222-222222222222",
        )

        service.send_member_added_email(project=project, member=member, added_by=actor)

        notifications_service.send_email.assert_not_called()

    @pytest.mark.django_db
    def test_send_member_added_email_raises_project_error_when_notify_fails(self):
        notifications_service = Mock(spec=GovUKNotificationsService)
        notifications_service.send_email.side_effect = GovUKNotificationError("Notify failed")
        project = baker.make("projects.Project", name="My Project")
        member = baker.make("users.User", email="member.added@example.com")
        actor = baker.make("users.User", email="actor@example.com")
        service = ProjectMembershipNotificationService(
            notifications_service=notifications_service,
            member_added_template_id="11111111-1111-1111-1111-111111111111",
            member_removed_template_id="22222222-2222-2222-2222-222222222222",
        )

        with pytest.raises(ProjectNotificationError):
            service.send_member_added_email(project=project, member=member, added_by=actor)
