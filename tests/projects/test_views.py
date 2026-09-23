import uuid
from unittest.mock import patch

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.urls import reverse
from model_bakery import baker
from pytest_django.asserts import assertContains, assertInHTML, assertNotContains

from ai_gateway.exceptions import AIGatewayAPIError
from projects.graph import EntraAuthenticationError, EntraRequestError
from projects.models import Project, ProjectMembership, ProjectPermission
from projects.services import ProjectNotificationError
from users.models import User


def member_selection(user, permissions=None):
    """Build a session/POST selection payload for ``user``'s Entra identity."""
    return {
        "oid": str(user.oid),
        "email": user.email,
        "display_name": user.full_name,
        "permissions": permissions or [],
    }


class TestDetailView:
    """Tests for the ProjectDetailView at '/projects/<uuid>/'."""

    def test_detail_page_renders(self, client, project, project_member):
        client.force_login(project_member)
        response = client.get(reverse("projects:project_detail", args=[project.uuid]))
        current_overview_link = (
            f'<a href="{reverse("projects:project_detail", args=[project.uuid])}" '
            'aria-current="location">Overview</a>'
        )

        assert response.status_code == 200
        assert "projects/detail.html" in [t.name for t in response.templates]
        assertContains(response, 'aria-current="location"', count=1)
        assertInHTML(current_overview_link, response.content.decode())

    def test_detail_page_fail(self, client, non_project_user, project):
        client.force_login(non_project_user)
        response = client.get(reverse("projects:project_detail", args=[project.uuid]))

        assert response.status_code == 404

    def test_superuser_can_view_project_without_membership(self, client, superuser, project):
        client.force_login(superuser)

        response = client.get(reverse("projects:project_detail", args=[project.uuid]))

        assert response.status_code == 200


class TestProjectUsersListView:
    """Tests for the ProjectUsersListView at '/projects/<uuid>/users/'"""

    def test_users_page_renders_with_members_active(self, client, project, project_member):
        client.force_login(project_member)
        response = client.get(reverse("projects:project_users", args=[project.uuid]))
        current_members_link = (
            f'<a href="{reverse("projects:project_users", args=[project.uuid])}" '
            'aria-current="location">Project members</a>'
        )

        assert response.status_code == 200
        assert "projects/member_list.html" in [t.name for t in response.templates]
        assertContains(response, 'aria-current="location"', count=1)
        assertInHTML(current_members_link, response.content.decode())

    def test_superuser_can_view_members_without_membership(self, client, superuser, project):
        client.force_login(superuser)

        response = client.get(reverse("projects:project_users", args=[project.uuid]))

        assert response.status_code == 200

    def test_users_page_does_not_render_for_non_member(self, client, project, non_project_user):
        client.force_login(non_project_user)
        response = client.get(reverse("projects:project_users", args=[project.uuid]))

        assert response.status_code == 404

    def test_owner_listed_first(self, client, project, project_owner, project_member):
        client.force_login(project_owner)
        response = client.get(reverse("projects:project_users", args=[project.uuid]))

        assert response.status_code == 200
        assert project_owner.email != project_member.email
        content = response.content.decode()
        owner_index = content.find(project_owner.email)
        member_index = content.find(project_member.email)
        assert owner_index < member_index


class TestProjectDeleteView:
    """Tests for the ProjectDeleteView at '/projects/<uuid>/delete'."""

    def test_delete_page_renders(self, client, user, project):
        client.force_login(user)
        response = client.get(reverse("projects:project_delete", args=[project.uuid]))

        assert response.status_code == 200
        assert "projects/delete_confirm.html" in [t.name for t in response.templates]

    def test_delete_page_fail(self, client, non_project_user, project):
        client.force_login(non_project_user)
        response = client.get(reverse("projects:project_delete", args=[project.uuid]))

        assert response.status_code == 404

    def test_project_owner_can_delete_project(self, client, project, project_owner, key_service):
        client.force_login(project_owner)
        response = client.get(reverse("projects:project_delete", args=[project.uuid]))
        assert response.status_code == 200

        response = client.post(reverse("projects:project_delete", args=[project.uuid]))
        assert response.status_code == 302
        assert Project.objects.filter(id=project.id).exists() is False
        # no keys to delete
        key_service.bulk_delete_keys.assert_not_called()
        key_service.delete_team.assert_not_called()

    def test_superuser_can_delete_project(self, client, project, superuser, key_service):
        client.force_login(superuser)
        response = client.get(reverse("projects:project_delete", args=[project.uuid]))
        assert response.status_code == 200

        response = client.post(reverse("projects:project_delete", args=[project.uuid]))
        assert response.status_code == 302
        assert Project.objects.filter(id=project.id).exists() is False
        # no keys to delete
        key_service.bulk_delete_keys.assert_not_called()
        key_service.delete_team.assert_not_called()

    def test_project_member_cannot_delete_project(
        self, client, project, project_member, key_service
    ):
        client.force_login(project_member)
        response = client.get(reverse("projects:project_delete", args=[project.uuid]))
        assert response.status_code == 404

        response = client.post(reverse("projects:project_delete", args=[project.uuid]))
        assert response.status_code == 404
        assert Project.objects.filter(id=project.id).exists()
        key_service.bulk_delete_keys.assert_not_called()
        key_service.delete_team.assert_not_called()

    def test_delete_project_deletes_gateway_keys_and_team(
        self, client, project, project_owner, key_service
    ):
        baker.make("ai_gateway.Team", project=project, litellm_team_id="team-123")
        baker.make(
            "ai_gateway.Key",
            project=project,
            litellm_secret="sk-secret-1",
            created_by=project_owner,
        )
        baker.make(
            "ai_gateway.Key",
            project=project,
            litellm_secret="sk-secret-2",
            created_by=project_owner,
        )

        client.force_login(project_owner)
        response = client.post(reverse("projects:project_delete", args=[project.uuid]))

        assert response.status_code == 302
        assert not Project.objects.filter(id=project.id).exists()
        key_service.bulk_delete_keys.assert_called_once()
        key_service.delete_team.assert_called_once_with("team-123")

        deleted_keys = key_service.bulk_delete_keys.call_args.args[0]
        assert sorted(deleted_keys) == ["sk-secret-1", "sk-secret-2"]

    def test_gateway_error_on_bulk_delete_keys_aborts_project_deletion(
        self, client, project, project_owner, key_service
    ):
        baker.make("ai_gateway.Team", project=project, litellm_team_id="team-123")
        baker.make(
            "ai_gateway.Key",
            project=project,
            litellm_secret="sk-secret-1",
            created_by=project_owner,
        )
        key_service.bulk_delete_keys.side_effect = AIGatewayAPIError(500, "gateway error")

        client.force_login(project_owner)
        response = client.post(reverse("projects:project_delete", args=[project.uuid]))

        assert response.status_code == 302
        assert response.url == reverse("projects:project_detail", args=[project.uuid])
        assert Project.objects.filter(id=project.id).exists()
        key_service.delete_team.assert_not_called()

    def test_gateway_error_on_delete_team_aborts_project_deletion(
        self, client, project, project_owner, key_service
    ):
        baker.make("ai_gateway.Team", project=project, litellm_team_id="team-123")
        baker.make(
            "ai_gateway.Key",
            project=project,
            litellm_secret="sk-secret-1",
            created_by=project_owner,
        )
        key_service.delete_team.side_effect = AIGatewayAPIError(500, "gateway error")

        client.force_login(project_owner)
        response = client.post(reverse("projects:project_delete", args=[project.uuid]))

        assert response.status_code == 302
        assert response.url == reverse("projects:project_detail", args=[project.uuid])
        assert Project.objects.filter(id=project.id).exists()


class TestProjectRemoveUserView:
    """Tests for the ProjectRemoveUserView at '/projects/<uuid>/users/<user_id>/remove/'."""

    @pytest.fixture(autouse=True)
    def _grant_manage_members(self, project, project_owner, grant_project_permission):
        grant_project_permission(project, project_owner, ProjectPermission.MANAGE_MEMBERS)

    def test_remove_user_page_renders(self, client, project, project_owner, project_member):
        client.force_login(project_owner)
        response = client.get(
            reverse("projects:project_user_remove", args=[project.uuid, project_member.id])
        )

        assert response.status_code == 200
        assert "projects/member_remove_confirm.html" in [t.name for t in response.templates]

    def test_remove_user_page_fail(self, client, non_project_user, project):
        client.force_login(non_project_user)
        response = client.get(
            reverse("projects:project_user_remove", args=[project.uuid, non_project_user.id])
        )

        assert response.status_code == 404

    def test_remove_user_page_denied_without_manage_members_permission(
        self, client, project, project_member_without_permissions
    ):
        client.force_login(project_member_without_permissions)

        response = client.get(
            reverse(
                "projects:project_user_remove",
                args=[project.uuid, project_member_without_permissions.id],
            )
        )

        assert response.status_code == 403

    def test_remove_other_user_redirects_to_project_users(
        self, client, user, project, project_membership_notification_service
    ):
        other_user = baker.make("users.User", first_name="Jane", last_name="Doe")
        baker.make(
            "projects.ProjectMembership",
            project=project,
            user=other_user,
        )
        client.force_login(user)

        response = client.post(
            reverse("projects:project_user_remove", args=[project.uuid, other_user.id])
        )

        assert response.status_code == 302
        assert response.url == reverse("projects:project_users", args=[project.uuid])
        assert not ProjectMembership.objects.filter(project=project, user=other_user).exists()
        project_membership_notification_service.send_member_removed_email.assert_called_once_with(
            project=project,
            member=other_user,
            removed_by=user,
        )

    def test_remove_self_redirects_to_projects_list(
        self,
        client,
        user,
        project,
        project_owner,
        project_member,
        project_membership_notification_service,
        grant_project_permission,
    ):
        grant_project_permission(
            project,
            project_member,
            ProjectPermission.MANAGE_MEMBERS,
        )
        client.force_login(project_member)

        response = client.post(
            reverse("projects:project_user_remove", args=[project.uuid, project_member.id])
        )

        assert response.status_code == 302
        assert response.url == reverse("projects:projects_list")
        assert not ProjectMembership.objects.filter(project=project, user=project_member).exists()
        project_membership_notification_service.send_member_removed_email.assert_called_once_with(
            project=project,
            member=project_member,
            removed_by=project_member,
        )

    def test_remove_member_continues_when_notification_fails(
        self,
        client,
        project,
        project_owner,
        project_member,
        project_membership_notification_service,
    ):
        project_membership_notification_service.send_member_removed_email.side_effect = (
            ProjectNotificationError("Notify failed")
        )

        client.force_login(project_owner)
        with patch("projects.views.sentry_sdk.capture_exception") as capture_exception:
            response = client.post(
                reverse("projects:project_user_remove", args=[project.uuid, project_member.id])
            )

        assert response.status_code == 302
        assert response.url == reverse("projects:project_users", args=[project.uuid])
        assert not ProjectMembership.objects.filter(project=project, user=project_member).exists()
        capture_exception.assert_called_once()

    def test_removing_owner_returns_404(
        self, client, project, project_owner, project_member, grant_project_permission
    ):
        grant_project_permission(
            project,
            project_member,
            ProjectPermission.MANAGE_MEMBERS,
        )
        client.force_login(project_member)

        response = client.post(
            reverse("projects:project_user_remove", args=[project.uuid, project_owner.id])
        )

        assert response.status_code == 404


class TestProjectAddUsersFlow:
    """Tests for the ProjectAddUsersView and ProjectAddUsersReviewView."""

    @pytest.fixture(autouse=True)
    def _grant_manage_members(self, project, project_owner, grant_project_permission):
        grant_project_permission(project, project_owner, ProjectPermission.MANAGE_MEMBERS)

    def test_add_member_page_renders(self, client, project, project_owner):
        client.force_login(project_owner)

        response = client.get(reverse("projects:project_users_add", args=[project.uuid]))

        assert response.status_code == 200
        assert "projects/member_add.html" in [t.name for t in response.templates]

    def test_add_member_page_fail(self, client, non_project_user, project):
        client.force_login(non_project_user)

        response = client.get(reverse("projects:project_users_add", args=[project.uuid]))

        assert response.status_code == 404

    def test_add_users_page_denied_without_manage_members_permission(
        self, client, project, project_member_without_permissions
    ):
        client.force_login(project_member_without_permissions)

        response = client.get(reverse("projects:project_users_add", args=[project.uuid]))

        assert response.status_code == 403

    def test_review_page_denied_without_manage_members_permission(
        self, client, project, project_member_without_permissions
    ):
        client.force_login(project_member_without_permissions)

        response = client.get(reverse("projects:project_users_add_review", args=[project.uuid]))

        assert response.status_code == 403

    def test_add_member_page_context_contains_form(self, client, project, project_owner):
        client.force_login(project_owner)

        response = client.get(reverse("projects:project_users_add", args=[project.uuid]))

        assert response.status_code == 200
        assert "form" in response.context

    def test_add_member_page_prefills_when_editing(self, client, project, project_owner):
        selected_user = baker.make("users.User", email="editable.member@example.com")
        client.force_login(project_owner)

        session = client.session
        session["project_user_add_selection"] = {
            f"project:{project.id}": [
                member_selection(selected_user, permissions=["manage_api_keys"])
            ]
        }
        session.save()

        response = client.get(
            reverse("projects:project_users_add", args=[project.uuid]),
            {"edit": str(selected_user.oid)},
        )

        assert response.status_code == 200
        form = response.context["form"]
        assert form.initial["oid"] == str(selected_user.oid)
        assert form.initial["permissions"] == ["manage_api_keys"]

    def test_add_member_submits_and_redirects_to_review(self, client, project, project_owner):
        user_to_add = baker.make("users.User", email="member.one@example.com")
        client.force_login(project_owner)

        response = client.post(
            reverse("projects:project_users_add", args=[project.uuid]),
            data={
                "oid": str(user_to_add.oid),
                "email": user_to_add.email,
                "permissions": ["manage_members"],
            },
        )

        assert response.status_code == 302
        assert response.url == reverse("projects:project_users_add_review", args=[project.uuid])

        session = client.session
        stored = session["project_user_add_selection"][f"project:{project.id}"]
        assert stored == [member_selection(user_to_add, permissions=["manage_members"])]

    def test_add_member_rejects_duplicate_already_selected(self, client, project, project_owner):
        already_selected = baker.make("users.User", email="member.two@example.com")
        client.force_login(project_owner)

        session = client.session
        session["project_user_add_selection"] = {
            f"project:{project.id}": [member_selection(already_selected)]
        }
        session.save()

        response = client.post(
            reverse("projects:project_users_add", args=[project.uuid]),
            data={"oid": str(already_selected.oid)},
        )

        assert response.status_code == 200
        assert "This person has already been added" in response.content.decode()

    def test_review_page_renders_selected_members(self, client, project, project_owner):
        selected_user = baker.make("users.User", email="member.three@example.com")
        client.force_login(project_owner)
        session = client.session
        session["project_user_add_selection"] = {
            f"project:{project.id}": [
                member_selection(selected_user, permissions=["manage_members"])
            ]
        }
        session.save()

        response = client.get(reverse("projects:project_users_add_review", args=[project.uuid]))

        assert response.status_code == 200
        assert "projects/member_add_review.html" in [t.name for t in response.templates]
        assert selected_user.email in response.content.decode()
        assert "Manage Members" in response.content.decode()

    def test_review_page_redirects_to_add_member_when_empty(self, client, project, project_owner):
        client.force_login(project_owner)

        response = client.get(reverse("projects:project_users_add_review", args=[project.uuid]))

        assert response.status_code == 302
        assert response.url == reverse("projects:project_users_add", args=[project.uuid])

    def test_review_removes_member(self, client, project, project_owner):
        keep_user = baker.make("users.User", email="keep.member@example.com")
        remove_user = baker.make("users.User", email="remove.member@example.com")
        client.force_login(project_owner)
        session = client.session
        session["project_user_add_selection"] = {
            f"project:{project.id}": [member_selection(keep_user), member_selection(remove_user)]
        }
        session.save()

        response = client.post(
            reverse("projects:project_users_add_review", args=[project.uuid]),
            data={"remove_oid": str(remove_user.oid)},
        )

        assert response.status_code == 302
        assert response.url == reverse("projects:project_users_add_review", args=[project.uuid])
        session = client.session
        stored = session["project_user_add_selection"][f"project:{project.id}"]
        assert stored == [member_selection(keep_user)]

    def test_review_continue_adds_users_to_project(
        self,
        client,
        django_capture_on_commit_callbacks,
        project_owner,
        project,
        project_membership_notification_service,
    ):

        selected_user = baker.make("users.User", email="member.four@example.com")
        client.force_login(project_owner)
        session = client.session
        session["project_user_add_selection"] = {
            f"project:{project.id}": [
                member_selection(selected_user, permissions=["manage_api_keys"])
            ]
        }
        session.save()

        with django_capture_on_commit_callbacks(execute=True):
            response = client.post(
                reverse("projects:project_users_add_review", args=[project.uuid])
            )

        assert response.status_code == 302
        assert response.url == reverse("projects:project_users", args=[project.uuid])
        membership = ProjectMembership.objects.get(project=project, user=selected_user)
        assert membership.permissions.filter(permission__codename="manage_api_keys").exists()
        project_membership_notification_service.send_member_added_email.assert_called_once_with(
            project=project,
            member=selected_user,
            added_by=project_owner,
        )

    def test_review_continue_continues_when_notification_fails(
        self,
        client,
        django_capture_on_commit_callbacks,
        project_owner,
        project,
        project_membership_notification_service,
    ):

        selected_user = baker.make("users.User", email="member.notify.fail@example.com")
        project_membership_notification_service.send_member_added_email.side_effect = (
            ProjectNotificationError("Notify failed")
        )
        client.force_login(project_owner)
        session = client.session
        session["project_user_add_selection"] = {
            f"project:{project.id}": [member_selection(selected_user)]
        }
        session.save()

        with (
            patch("projects.mixins.sentry_sdk.capture_exception") as capture_exception,
            django_capture_on_commit_callbacks(execute=True),
        ):
            response = client.post(
                reverse("projects:project_users_add_review", args=[project.uuid])
            )

        assert response.status_code == 302
        assert response.url == reverse("projects:project_users", args=[project.uuid])
        assert ProjectMembership.objects.filter(
            project=project,
            user=selected_user,
        ).exists()
        capture_exception.assert_called_once()

    def test_review_continue_captures_misconfigured_notification_service(
        self,
        client,
        django_capture_on_commit_callbacks,
        project_owner,
        project,
    ):

        selected_user = baker.make("users.User", email="member.config.fail@example.com")
        client.force_login(project_owner)
        session = client.session
        session["project_user_add_selection"] = {
            f"project:{project.id}": [member_selection(selected_user)]
        }
        session.save()

        with (
            patch(
                "projects.mixins.ProjectMembershipNotificationService.from_settings",
                side_effect=ImproperlyConfigured("Missing Notify settings"),
            ),
            patch("projects.mixins.sentry_sdk.capture_exception") as capture_exception,
            django_capture_on_commit_callbacks(execute=True),
        ):
            response = client.post(
                reverse("projects:project_users_add_review", args=[project.uuid])
            )

        assert response.status_code == 302
        assert response.url == reverse("projects:project_users", args=[project.uuid])
        assert ProjectMembership.objects.filter(
            project=project,
            user=selected_user,
        ).exists()
        capture_exception.assert_called_once()

    def test_review_continue_records_membership_history_with_user(
        self, client, project, project_owner
    ):
        """Regression: bulk_create_with_history must record history_user for added memberships."""
        selected_user = baker.make("users.User", email="history.add@example.com")
        client.force_login(project_owner)
        session = client.session
        session["project_user_add_selection"] = {
            f"project:{project.id}": [member_selection(selected_user)]
        }
        session.save()

        client.post(reverse("projects:project_users_add_review", args=[project.uuid]))

        membership = ProjectMembership.objects.get(project=project, user=selected_user)
        historical = membership.history.filter(history_type="+")
        assert historical.exists()
        assert historical.first().history_user == project_owner

    def test_review_continue_adds_new_entra_user_creates_stub_account(
        self,
        client,
        django_capture_on_commit_callbacks,
        project_owner,
        project,
        project_membership_notification_service,
    ):
        new_oid = str(uuid.uuid4())
        client.force_login(project_owner)
        session = client.session
        session["project_user_add_selection"] = {
            f"project:{project.id}": [
                {
                    "oid": new_oid,
                    "email": "new.hire@example.com",
                    "display_name": "New Hire",
                    "permissions": [],
                }
            ]
        }
        session.save()

        graph_user = {
            "id": new_oid,
            "mail": "new.hire@example.com",
            "givenName": "New",
            "surname": "Hire",
            "displayName": "New Hire",
        }

        with (
            patch("projects.services.MicrosoftGraphClient.from_request") as from_request,
            django_capture_on_commit_callbacks(execute=True),
        ):
            from_request.return_value.get_user.return_value = graph_user
            response = client.post(
                reverse("projects:project_users_add_review", args=[project.uuid])
            )

        assert response.status_code == 302
        from_request.return_value.get_user.assert_called_once_with(new_oid)
        created_user = User.objects.get(oid=new_oid)
        assert created_user.email == "new.hire@example.com"
        assert created_user.first_name == "New"
        assert created_user.last_name == "Hire"
        assert ProjectMembership.objects.filter(
            project=project,
            user=created_user,
        ).exists()

    def test_review_continue_redirects_when_entra_auth_missing(
        self, client, project, project_owner
    ):
        new_oid = str(uuid.uuid4())
        client.force_login(project_owner)
        session = client.session
        session["project_user_add_selection"] = {
            f"project:{project.id}": [
                {"oid": new_oid, "email": "x@example.com", "display_name": "X", "permissions": []}
            ]
        }
        session.save()

        with patch("projects.services.MicrosoftGraphClient.from_request") as from_request:
            from_request.side_effect = EntraAuthenticationError("no token")
            response = client.post(
                reverse("projects:project_users_add_review", args=[project.uuid])
            )

        assert response.status_code == 302
        assert response.url == reverse("projects:project_users_add", args=[project.uuid])
        assert not User.objects.filter(oid=new_oid).exists()
        assert "error_message" in client.session

    def test_review_continue_redirects_when_entra_lookup_fails(
        self, client, project, project_owner
    ):
        new_oid = str(uuid.uuid4())
        client.force_login(project_owner)
        session = client.session
        session["project_user_add_selection"] = {
            f"project:{project.id}": [
                {"oid": new_oid, "email": "x@example.com", "display_name": "X", "permissions": []}
            ]
        }
        session.save()

        with (
            patch("projects.services.MicrosoftGraphClient.from_request") as from_request,
            patch("projects.views.sentry_sdk.capture_exception") as capture_exception,
        ):
            from_request.return_value.get_user.side_effect = EntraRequestError("boom")
            response = client.post(
                reverse("projects:project_users_add_review", args=[project.uuid])
            )

        assert response.status_code == 302
        assert response.url == reverse("projects:project_users_add", args=[project.uuid])
        assert not User.objects.filter(oid=new_oid).exists()
        capture_exception.assert_called_once()


class TestProjectMemberDetailView:
    def test_finds_member(self, client, project, project_owner):
        client.force_login(project_owner)
        membership = ProjectMembership.objects.get(
            project=project,
            user=project_owner,
        )
        response = client.get(
            reverse("projects:project_member_detail", args=[project.uuid, membership.pk])
        )

        assert response.status_code == 200
        assert "membership" in response.context
        assert response.context["membership"] == membership

    def test_member_without_permission(self, client, project, project_member):
        client.force_login(project_member)
        membership = ProjectMembership.objects.get(
            project=project,
            user=project_member,
        )
        response = client.get(
            reverse("projects:project_member_detail", args=[project.uuid, membership.pk])
        )

        assert response.status_code == 403

    def test_other_project_member_not_found(
        self, client, project, project_owner, non_project_user
    ):
        client.force_login(project_owner)
        other_project = baker.make("projects.Project")
        membership = ProjectMembership.objects.create(
            project=other_project,
            user=non_project_user,
        )
        response = client.get(
            reverse("projects:project_member_detail", args=[project.uuid, membership.pk])
        )

        assert response.status_code == 404


class TestProjectsListView:
    """Tests for the login-protected projects ListView."""

    def test_redirects_anonymous_user_to_login(self, client):
        response = client.get(reverse("projects:projects_list"))

        assert response.status_code == 302
        assert response.url.startswith(reverse("login"))

    def test_renders_for_authenticated_user(self, client, user):
        client.force_login(user)

        response = client.get(reverse("projects:projects_list"))

        assert response.status_code == 200

    def test_does_not_list_projects_without_membership(self, client, superuser, project):
        client.force_login(superuser)

        response = client.get(reverse("projects:projects_list"))

        assert response.status_code == 200
        assertNotContains(response, project.name)


class TestProjectCreateFlow:
    """Tests for ProjectCreateView, ProjectCreateAddUsersView, and ProjectCreateConfirmView."""

    def test_create_page_renders(self, client, user):
        client.force_login(user)

        response = client.get(reverse("projects:project_create"))

        assert response.status_code == 200
        assert "projects/create.html" in [t.name for t in response.templates]

    def test_create_page_repopulates_from_session(self, client, user):
        business_unit = baker.make("projects.BusinessUnit")
        client.force_login(user)

        session = client.session
        session["project_create"] = {
            "name": "Session Project",
            "description": "Saved description",
            "business_unit_id": business_unit.id,
        }
        session.save()

        response = client.get(reverse("projects:project_create"))

        assert response.status_code == 200
        form = response.context["form"]
        assert form.initial["name"] == "Session Project"
        assert form.initial["description"] == "Saved description"
        assert form.initial["business_unit"] == business_unit.id

    def test_create_post_stores_session_and_redirects(self, client, user):
        business_unit = baker.make("projects.BusinessUnit")
        client.force_login(user)

        response = client.post(
            reverse("projects:project_create"),
            data={
                "name": "Create Wizard Project",
                "description": "Project description",
                "business_unit": business_unit.id,
            },
        )

        assert response.status_code == 302
        assert response.url == reverse("projects:project_create_add_users")

        session = client.session
        assert session["project_create"] == {
            "name": "Create Wizard Project",
            "description": "Project description",
            "business_unit_id": business_unit.id,
        }

    def test_create_add_users_page_renders(self, client, user):
        client.force_login(user)

        response = client.get(reverse("projects:project_create_add_users"))

        assert response.status_code == 200
        assert "projects/create_member_add.html" in [t.name for t in response.templates]
        assert "form" in response.context

    def test_create_add_users_shows_decision_error_when_missing(self, client, user):
        client.force_login(user)

        response = client.post(reverse("projects:project_create_add_users"), data={})

        assert response.status_code == 200
        assert "Choose yes or no" in response.content.decode()

    def test_create_add_users_no_redirects_and_clears_selection(self, client, user):
        selected_user = baker.make("users.User", email="skip.member@example.com")
        client.force_login(user)

        session = client.session
        session["project_user_add_selection"] = {
            "project_create_user_add": [member_selection(selected_user)]
        }
        session.save()

        response = client.post(
            reverse("projects:project_create_add_users"),
            data={"add_user": "no"},
        )

        assert response.status_code == 302
        assert response.url == reverse("projects:project_create_confirm")

        session = client.session
        assert session["project_user_add_selection"] == {}

    def test_create_add_users_yes_redirects_to_add_member(self, client, user):
        client.force_login(user)

        response = client.post(
            reverse("projects:project_create_add_users"),
            data={"add_user": "yes"},
        )

        assert response.status_code == 302
        assert response.url == reverse("projects:project_create_add_member")

    def test_create_add_users_prefills_yes_when_selection_exists(self, client, user):
        selected_user = baker.make("users.User", email="existing.selection@example.com")
        client.force_login(user)

        session = client.session
        session["project_user_add_selection"] = {
            "project_create_user_add": [member_selection(selected_user)]
        }
        session.save()

        response = client.get(reverse("projects:project_create_add_users"))

        assert response.status_code == 200
        assert response.context["form"]["add_user"].value() == "yes"

    def test_create_add_member_page_renders(self, client, user):
        client.force_login(user)

        response = client.get(reverse("projects:project_create_add_member"))

        assert response.status_code == 200
        assert "projects/member_add.html" in [t.name for t in response.templates]

    def test_create_add_member_submits_and_redirects_to_review(self, client, user):
        selected_user = baker.make("users.User", email="create.member@example.com")
        client.force_login(user)

        response = client.post(
            reverse("projects:project_create_add_member"),
            data={
                "oid": str(selected_user.oid),
                "email": selected_user.email,
                "display_name": selected_user.full_name,
                "permissions": ["manage_members"],
            },
        )

        assert response.status_code == 302
        assert response.url == reverse("projects:project_create_review_members")

        session = client.session
        assert session["project_user_add_selection"]["project_create_user_add"] == [
            member_selection(selected_user, permissions=["manage_members"])
        ]

    def test_create_review_members_page_renders(self, client, user):
        selected_user = baker.make("users.User", email="review.member@example.com")
        client.force_login(user)
        session = client.session
        session["project_user_add_selection"] = {
            "project_create_user_add": [
                member_selection(selected_user, permissions=["manage_api_keys"])
            ]
        }
        session.save()

        response = client.get(reverse("projects:project_create_review_members"))

        assert response.status_code == 200
        assert "projects/create_review_members.html" in [t.name for t in response.templates]
        assert selected_user.email in response.content.decode()
        assert "Manage API Keys" in response.content.decode()

    def test_create_review_members_removes_member(self, client, user):
        keep_user = baker.make("users.User", email="keep.create@example.com")
        remove_user = baker.make("users.User", email="remove.create@example.com")
        client.force_login(user)
        session = client.session
        session["project_user_add_selection"] = {
            "project_create_user_add": [
                member_selection(keep_user),
                member_selection(remove_user),
            ]
        }
        session.save()

        response = client.post(
            reverse("projects:project_create_review_members"),
            data={"remove_oid": str(remove_user.oid)},
        )

        assert response.status_code == 302
        session = client.session
        stored = session["project_user_add_selection"]["project_create_user_add"]
        assert stored == [member_selection(keep_user)]

    def test_create_confirm_page_renders_project_data_and_members(self, client, user):
        business_unit = baker.make("projects.BusinessUnit", name="Data Unit")
        selected_user = baker.make("users.User", email="confirm.member@example.com")
        client.force_login(user)

        session = client.session
        session["project_create"] = {
            "name": "Confirm Project",
            "description": "Confirm description",
            "business_unit_id": business_unit.id,
        }
        session["project_user_add_selection"] = {
            "project_create_user_add": [
                member_selection(selected_user, permissions=["manage_members"])
            ]
        }
        session.save()

        response = client.get(reverse("projects:project_create_confirm"))

        assert response.status_code == 200
        assert "projects/create_confirm.html" in [t.name for t in response.templates]
        assert "Confirm Project" in response.content.decode()
        assert business_unit.name in response.content.decode()
        assert selected_user.email in response.content.decode()
        assert "Manage Members" in response.content.decode()

    def test_create_confirm_post_creates_project_and_memberships(self, client, user):
        business_unit = baker.make("projects.BusinessUnit")
        selected_user = baker.make("users.User", email="create.final@example.com")
        client.force_login(user)

        session = client.session
        session["project_create"] = {
            "name": "Final Creation Project",
            "description": "Final description",
            "business_unit_id": business_unit.id,
        }
        session["project_user_add_selection"] = {
            "project_create_user_add": [
                member_selection(selected_user, permissions=["manage_api_keys"])
            ]
        }
        session.save()

        response = client.post(reverse("projects:project_create_confirm"))

        project = Project.objects.get(name="Final Creation Project")
        assert response.status_code == 302
        assert response.url == reverse("projects:project_detail", args=[project.uuid])
        membership = ProjectMembership.objects.get(project=project, user=selected_user)
        assert membership.permissions.filter(permission__codename="manage_api_keys").exists()
        assert "project_create" not in client.session
        assert "project_user_add_selection" not in client.session

    def test_create_confirm_post_grants_creator_all_permissions(self, client, user):
        business_unit = baker.make("projects.BusinessUnit")
        client.force_login(user)

        session = client.session
        session["project_create"] = {
            "name": "Creator Permissions Project",
            "description": "desc",
            "business_unit_id": business_unit.id,
        }
        session.save()

        client.post(reverse("projects:project_create_confirm"))

        project = Project.objects.get(name="Creator Permissions Project")
        membership = ProjectMembership.objects.get(project=project, user=user)
        granted = set(membership.permissions.values_list("permission__codename", flat=True))
        assert granted == {"manage_api_keys", "manage_members"}

    def test_create_confirm_post_records_membership_history_with_user(self, client, user):
        """Regression: bulk_create_with_history must record history_user for new memberships."""
        business_unit = baker.make("projects.BusinessUnit")
        selected_user = baker.make("users.User", email="history.member@example.com")
        client.force_login(user)

        session = client.session
        session["project_create"] = {
            "name": "History Test Project",
            "description": "desc",
            "business_unit_id": business_unit.id,
        }
        session["project_user_add_selection"] = {
            "project_create_user_add": [member_selection(selected_user)]
        }
        session.save()

        client.post(reverse("projects:project_create_confirm"))

        project = Project.objects.get(name="History Test Project")
        for membership in ProjectMembership.objects.filter(project=project):
            historical = membership.history.filter(history_type="+")
            assert historical.exists(), f"No creation history record for user {membership.user}"
            assert historical.first().history_user == user
