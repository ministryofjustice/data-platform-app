from unittest.mock import Mock, patch

import pytest
from django.core.exceptions import ImproperlyConfigured
from model_bakery import baker
from notifications_python_client.errors import HTTPError

from data_platform_app.services import GovUKNotificationError, GovUKNotificationsService
from projects.graph import EntraAuthenticationError, EntraRequestError
from projects.models import ProjectUserPermissions
from projects.services import (
    ProjectMembershipNotificationService,
    ProjectNotificationError,
    ProjectService,
)
from users.models import User


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


def _graph_payload(oid, *, mail="new.hire@example.com"):
    return {
        "id": oid,
        "mail": mail,
        "givenName": "New",
        "surname": "Hire",
        "displayName": "New Hire",
    }


@pytest.mark.django_db
class TestProjectService:
    def test_add_members_reuses_existing_users_without_graph_calls(
        self, project, user, non_project_user
    ):
        graph_client = Mock()
        service = ProjectService(graph_client=graph_client)

        added = service.add_members(
            project=project,
            selections=[{"oid": str(non_project_user.oid)}],
            added_by=user,
        )

        graph_client.get_user.assert_not_called()
        assert [member.oid for member in added] == [non_project_user.oid]
        assert ProjectUserPermissions.objects.filter(
            project=project, user=non_project_user
        ).exists()

    def test_add_members_is_idempotent_for_existing_membership(
        self, project, user, non_project_user
    ):
        service = ProjectService(graph_client=Mock())

        service.add_members(
            project=project,
            selections=[{"oid": str(user.oid)}],
            added_by=non_project_user,
        )

        assert ProjectUserPermissions.objects.filter(project=project, user=user).count() == 1

    def test_add_members_creates_stub_for_unknown_oid(self, project, user):
        new_oid = str(baker.make("users.User").oid)
        User.objects.filter(oid=new_oid).delete()
        graph_client = Mock()
        graph_client.get_user.return_value = _graph_payload(new_oid)
        service = ProjectService(graph_client=graph_client)

        added = service.add_members(
            project=project,
            selections=[{"oid": new_oid}],
            added_by=user,
        )

        graph_client.get_user.assert_called_once_with(new_oid)
        created = User.objects.get(oid=new_oid)
        assert created.email == "new.hire@example.com"
        assert created.first_name == "New"
        assert created.last_name == "Hire"
        assert [str(member.oid) for member in added] == [new_oid]
        assert ProjectUserPermissions.objects.filter(project=project, user=created).exists()

    def test_add_members_propagates_graph_errors(self, project, user):
        new_oid = str(baker.make("users.User").oid)
        User.objects.filter(oid=new_oid).delete()
        graph_client = Mock()
        graph_client.get_user.side_effect = EntraRequestError("boom")
        service = ProjectService(graph_client=graph_client)

        with pytest.raises(EntraRequestError):
            service.add_members(
                project=project,
                selections=[{"oid": new_oid}],
                added_by=user,
            )

    def test_from_request_propagates_authentication_error(self, project, user):
        new_oid = str(baker.make("users.User").oid)
        User.objects.filter(oid=new_oid).delete()
        service = ProjectService.from_request(request=object())

        with (
            patch(
                "projects.services.MicrosoftGraphClient.from_request",
                side_effect=EntraAuthenticationError("no token"),
            ),
            pytest.raises(EntraAuthenticationError),
        ):
            service.add_members(
                project=project,
                selections=[{"oid": new_oid}],
                added_by=user,
            )

    def test_create_project_adds_owner_and_selected_members(self, user, non_project_user):
        business_unit = baker.make("projects.BusinessUnit")
        service = ProjectService(graph_client=Mock())

        project, members = service.create_project(
            name="My Project",
            description="A description",
            business_unit_id=business_unit.id,
            created_by=user,
            selected_members=[{"oid": str(non_project_user.oid)}],
        )

        assert project.name == "My Project"
        assert project.created_by == user
        assert {member.oid for member in members} == {user.oid, non_project_user.oid}
        assert ProjectUserPermissions.objects.filter(project=project, user=user).exists()
        assert ProjectUserPermissions.objects.filter(
            project=project, user=non_project_user
        ).exists()

    def test_create_project_includes_owner_when_no_members_selected(self, user):
        business_unit = baker.make("projects.BusinessUnit")
        service = ProjectService(graph_client=Mock())

        project, members = service.create_project(
            name="Solo Project",
            description="A description",
            business_unit_id=business_unit.id,
            created_by=user,
            selected_members=[],
        )

        assert [member.oid for member in members] == [user.oid]
        assert ProjectUserPermissions.objects.filter(project=project, user=user).exists()

    def test_close_closes_graph_client(self):
        graph_client = Mock()
        service = ProjectService(graph_client=graph_client)

        service.close()

        graph_client.close.assert_called_once_with()
