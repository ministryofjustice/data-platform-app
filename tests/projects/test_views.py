from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.urls import reverse
from model_bakery import baker
from pytest_django.asserts import assertContains, assertInHTML

from ai_gateway.exceptions import AIGatewayAPIError
from projects.models import Project, ProjectUserPermissions
from projects.services import ProjectNotificationError


class TestDetailView:
    """Tests for the ProjectDetailView at '/projects/<uuid>/'."""

    def test_detail_page_renders(self, client, user, project):
        client.force_login(user)
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


class TestProjectUsersDetailView:
    """Tests for the ProjectUsersDetailView at '/projects/<uuid>/users/'"""

    def test_users_page_renders_with_members_active(self, client, user, project):
        client.force_login(user)
        response = client.get(reverse("projects:project_users", args=[project.uuid]))
        current_members_link = (
            f'<a href="{reverse("projects:project_users", args=[project.uuid])}" '
            'aria-current="location">Project members</a>'
        )

        assert response.status_code == 200
        assert "projects/user_list.html" in [t.name for t in response.templates]
        assertContains(response, 'aria-current="location"', count=1)
        assertInHTML(current_members_link, response.content.decode())


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

    def test_delete_project(self, client, user, project, key_service):
        client.force_login(user)
        response = client.post(reverse("projects:project_delete", args=[project.uuid]))

        assert response.status_code == 302
        assert not Project.objects.filter(id=project.id).exists()
        key_service.bulk_delete_keys.assert_not_called()
        key_service.delete_team.assert_not_called()

    def test_delete_project_deletes_gateway_keys_and_team(
        self, client, user, project, key_service
    ):
        baker.make("ai_gateway.Team", project=project, litellm_team_id="team-123")
        baker.make(
            "ai_gateway.Key", project=project, litellm_secret="sk-secret-1", created_by=user
        )
        baker.make(
            "ai_gateway.Key", project=project, litellm_secret="sk-secret-2", created_by=user
        )

        client.force_login(user)
        response = client.post(reverse("projects:project_delete", args=[project.uuid]))

        assert response.status_code == 302
        assert not Project.objects.filter(id=project.id).exists()
        key_service.bulk_delete_keys.assert_called_once()
        key_service.delete_team.assert_called_once_with("team-123")

        deleted_keys = key_service.bulk_delete_keys.call_args.args[0]
        assert sorted(deleted_keys) == ["sk-secret-1", "sk-secret-2"]

    def test_gateway_error_on_bulk_delete_keys_aborts_project_deletion(
        self, client, user, project, key_service
    ):
        baker.make("ai_gateway.Team", project=project, litellm_team_id="team-123")
        baker.make(
            "ai_gateway.Key", project=project, litellm_secret="sk-secret-1", created_by=user
        )
        key_service.bulk_delete_keys.side_effect = AIGatewayAPIError(500, "gateway error")

        client.force_login(user)
        response = client.post(reverse("projects:project_delete", args=[project.uuid]))

        assert response.status_code == 302
        assert response.url == reverse("projects:project_detail", args=[project.uuid])
        assert Project.objects.filter(id=project.id).exists()
        key_service.delete_team.assert_not_called()

    def test_gateway_error_on_delete_team_aborts_project_deletion(
        self, client, user, project, key_service
    ):
        baker.make("ai_gateway.Team", project=project, litellm_team_id="team-123")
        baker.make(
            "ai_gateway.Key", project=project, litellm_secret="sk-secret-1", created_by=user
        )
        key_service.delete_team.side_effect = AIGatewayAPIError(500, "gateway error")

        client.force_login(user)
        response = client.post(reverse("projects:project_delete", args=[project.uuid]))

        assert response.status_code == 302
        assert response.url == reverse("projects:project_detail", args=[project.uuid])
        assert Project.objects.filter(id=project.id).exists()


class TestProjectRemoveUserView:
    """Tests for the ProjectRemoveUserView at '/projects/<uuid>/users/<user_id>/remove/'."""

    def test_remove_user_page_renders(self, client, user, project):
        client.force_login(user)
        response = client.get(
            reverse("projects:project_user_remove", args=[project.uuid, user.id])
        )

        assert response.status_code == 200
        assert "projects/user_remove_confirm.html" in [t.name for t in response.templates]

    def test_remove_user_page_fail(self, client, non_project_user, project):
        client.force_login(non_project_user)
        response = client.get(
            reverse("projects:project_user_remove", args=[project.uuid, non_project_user.id])
        )

        assert response.status_code == 404

    def test_remove_user(self, client, user, project, project_membership_notification_service):
        client.force_login(user)
        response = client.post(
            reverse("projects:project_user_remove", args=[project.uuid, user.id])
        )

        assert response.status_code == 302
        assert not ProjectUserPermissions.objects.filter(project=project, user=user).exists()
        project_membership_notification_service.send_member_removed_email.assert_called_once_with(
            project=project,
            member=user,
            removed_by=user,
        )

    def test_remove_user_continues_when_notification_fails(
        self,
        client,
        user,
        project,
        project_membership_notification_service,
    ):
        project_membership_notification_service.send_member_removed_email.side_effect = (
            ProjectNotificationError("Notify failed")
        )

        client.force_login(user)
        with patch("projects.views.sentry_sdk.capture_exception") as capture_exception:
            response = client.post(
                reverse("projects:project_user_remove", args=[project.uuid, user.id])
            )

        assert response.status_code == 302
        assert response.url == reverse("projects:project_users", args=[project.uuid])
        assert not ProjectUserPermissions.objects.filter(project=project, user=user).exists()
        capture_exception.assert_called_once()


class TestProjectAddUsersFlow:
    """Tests for the ProjectAddUsersView and ProjectAddUsersConfirmView."""

    def test_add_users_page_renders(self, client, user, project):
        client.force_login(user)

        response = client.get(reverse("projects:project_users_add", args=[project.uuid]))

        assert response.status_code == 200
        assert "projects/user_add.html" in [t.name for t in response.templates]

    def test_add_users_page_fail(self, client, non_project_user, project):
        client.force_login(non_project_user)

        response = client.get(reverse("projects:project_users_add", args=[project.uuid]))

        assert response.status_code == 404

    def test_add_users_page_context_contains_formset(self, client, user, project):
        client.force_login(user)

        response = client.get(reverse("projects:project_users_add", args=[project.uuid]))

        assert response.status_code == 200
        assert "formset" in response.context

    def test_add_users_page_repopulates_selected_users_from_session(self, client, user, project):
        selected_user_one = baker.make("users.User", email="member.five@example.com")
        selected_user_two = baker.make("users.User", email="member.six@example.com")
        client.force_login(user)

        session = client.session
        session["project_user_add_selection"] = {
            f"project:{project.id}": [selected_user_one.id, selected_user_two.id]
        }
        session.save()

        response = client.get(reverse("projects:project_users_add", args=[project.uuid]))

        assert response.status_code == 200
        formset = response.context["formset"]
        assert formset.total_form_count() == 2
        assert formset.forms[0].initial["user"] == selected_user_one.id
        assert formset.forms[1].initial["user"] == selected_user_two.id

    def test_add_users_page_submits_and_redirects_to_confirm(self, client, user, project):

        user_to_add = baker.make("users.User", email="member.one@example.com")
        client.force_login(user)

        response = client.post(
            reverse("projects:project_users_add", args=[project.uuid]),
            data={
                "members-TOTAL_FORMS": "1",
                "members-INITIAL_FORMS": "0",
                "members-MIN_NUM_FORMS": "0",
                "members-MAX_NUM_FORMS": "1000",
                "members-0-user": str(user_to_add.id),
            },
        )

        assert response.status_code == 302
        assert response.url == reverse("projects:project_users_add_confirm", args=[project.uuid])

    def test_add_users_page_excludes_existing_members_from_options(self, client, user, project):

        existing_member = baker.make("users.User", email="already.member@example.com")
        baker.make("users.User", email="new.member@example.com")
        baker.make(
            "projects.ProjectUserPermissions",
            project=project,
            user=existing_member,
            role="member",
        )

        client.force_login(user)
        response = client.get(reverse("projects:project_users_add", args=[project.uuid]))

        content = response.content.decode()
        assert response.status_code == 200
        assert "new.member@example.com" in content
        assert "already.member@example.com" not in content

    def test_add_users_page_rejects_duplicate_user_submission(self, client, user, project):

        user_to_add = baker.make("users.User", email="member.two@example.com")
        client.force_login(user)

        response = client.post(
            reverse("projects:project_users_add", args=[project.uuid]),
            data={
                "members-TOTAL_FORMS": "2",
                "members-INITIAL_FORMS": "0",
                "members-MIN_NUM_FORMS": "0",
                "members-MAX_NUM_FORMS": "1000",
                "members-0-user": str(user_to_add.id),
                "members-1-user": str(user_to_add.id),
            },
        )

        assert response.status_code == 200
        assert "You cannot add the same user more than once." in response.content.decode()

    def test_confirm_page_renders_selected_users(self, client, user, project):

        selected_user = baker.make("users.User", email="member.three@example.com")
        client.force_login(user)
        session = client.session
        session["project_user_add_selection"] = {f"project:{project.id}": [selected_user.id]}
        session.save()

        response = client.get(reverse("projects:project_users_add_confirm", args=[project.uuid]))

        assert response.status_code == 200
        assert "projects/user_add_confirm.html" in [t.name for t in response.templates]
        assert selected_user.email in response.content.decode()

    def test_confirm_adds_users_to_project(
        self,
        client,
        django_capture_on_commit_callbacks,
        user,
        project,
        project_membership_notification_service,
    ):

        selected_user = baker.make("users.User", email="member.four@example.com")
        client.force_login(user)
        session = client.session
        session["project_user_add_selection"] = {f"project:{project.id}": [selected_user.id]}
        session.save()

        with django_capture_on_commit_callbacks(execute=True):
            response = client.post(
                reverse("projects:project_users_add_confirm", args=[project.uuid])
            )

        assert response.status_code == 302
        assert response.url == reverse("projects:project_users", args=[project.uuid])
        assert ProjectUserPermissions.objects.filter(
            project=project,
            user=selected_user,
            role="admin",
        ).exists()
        project_membership_notification_service.send_member_added_email.assert_called_once_with(
            project=project,
            member=selected_user,
            added_by=user,
        )

    def test_confirm_adds_users_continues_when_notification_fails(
        self,
        client,
        django_capture_on_commit_callbacks,
        user,
        project,
        project_membership_notification_service,
    ):

        selected_user = baker.make("users.User", email="member.notify.fail@example.com")
        project_membership_notification_service.send_member_added_email.side_effect = (
            ProjectNotificationError("Notify failed")
        )
        client.force_login(user)
        session = client.session
        session["project_user_add_selection"] = {f"project:{project.id}": [selected_user.id]}
        session.save()

        with (
            patch("projects.mixins.sentry_sdk.capture_exception") as capture_exception,
            django_capture_on_commit_callbacks(execute=True),
        ):
            response = client.post(
                reverse("projects:project_users_add_confirm", args=[project.uuid])
            )

        assert response.status_code == 302
        assert response.url == reverse("projects:project_users", args=[project.uuid])
        assert ProjectUserPermissions.objects.filter(
            project=project,
            user=selected_user,
            role="admin",
        ).exists()
        capture_exception.assert_called_once()

    def test_confirm_adds_users_captures_misconfigured_notification_service(
        self,
        client,
        django_capture_on_commit_callbacks,
        user,
        project,
    ):

        selected_user = baker.make("users.User", email="member.config.fail@example.com")
        client.force_login(user)
        session = client.session
        session["project_user_add_selection"] = {f"project:{project.id}": [selected_user.id]}
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
                reverse("projects:project_users_add_confirm", args=[project.uuid])
            )

        assert response.status_code == 302
        assert response.url == reverse("projects:project_users", args=[project.uuid])
        assert ProjectUserPermissions.objects.filter(
            project=project,
            user=selected_user,
            role="admin",
        ).exists()
        capture_exception.assert_called_once()

    def test_confirm_adds_users_records_membership_history_with_user(self, client, user, project):
        """Regression: bulk_create_with_history must record history_user for added memberships."""
        selected_user = baker.make("users.User", email="history.add@example.com")
        client.force_login(user)
        session = client.session
        session["project_user_add_selection"] = {f"project:{project.id}": [selected_user.id]}
        session.save()

        client.post(reverse("projects:project_users_add_confirm", args=[project.uuid]))

        membership = ProjectUserPermissions.objects.get(project=project, user=selected_user)
        historical = membership.history.filter(history_type="+")
        assert historical.exists()
        assert historical.first().history_user == user


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
        assert "projects/create_user_add.html" in [t.name for t in response.templates]
        assert "decision_form" in response.context
        assert "formset" in response.context

    def test_create_add_users_shows_decision_error_when_missing(self, client, user):
        client.force_login(user)

        response = client.post(reverse("projects:project_create_add_users"), data={})

        assert response.status_code == 200
        assert "Choose yes or no" in response.content.decode()

    def test_create_add_users_no_redirects_and_clears_selection(self, client, user):
        selected_user = baker.make("users.User", email="skip.member@example.com")
        client.force_login(user)

        session = client.session
        session["project_user_add_selection"] = {"project_create_user_add": [selected_user.id]}
        session.save()

        response = client.post(
            reverse("projects:project_create_add_users"),
            data={"add_user": "no"},
        )

        assert response.status_code == 302
        assert response.url == reverse("projects:project_create_confirm")

        session = client.session
        assert session["project_user_add_selection"] == {}

    def test_create_add_users_yes_submits_and_stores_selection(self, client, user):
        selected_user = baker.make("users.User", email="create.member@example.com")
        client.force_login(user)

        response = client.post(
            reverse("projects:project_create_add_users"),
            data={
                "add_user": "yes",
                "members-TOTAL_FORMS": "1",
                "members-INITIAL_FORMS": "0",
                "members-MIN_NUM_FORMS": "0",
                "members-MAX_NUM_FORMS": "1000",
                "members-0-user": str(selected_user.id),
            },
        )

        assert response.status_code == 302
        assert response.url == reverse("projects:project_create_confirm")

        session = client.session
        assert session["project_user_add_selection"]["project_create_user_add"] == [
            selected_user.id
        ]

    def test_create_add_users_prefills_yes_when_selection_exists(self, client, user):
        selected_user = baker.make("users.User", email="existing.selection@example.com")
        client.force_login(user)

        session = client.session
        session["project_user_add_selection"] = {"project_create_user_add": [selected_user.id]}
        session.save()

        response = client.get(reverse("projects:project_create_add_users"))

        assert response.status_code == 200
        decision_form = response.context["decision_form"]
        assert decision_form["add_user"].value() == "yes"

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
        session["project_user_add_selection"] = {"project_create_user_add": [selected_user.id]}
        session.save()

        response = client.get(reverse("projects:project_create_confirm"))

        assert response.status_code == 200
        assert "projects/create_confirm.html" in [t.name for t in response.templates]
        assert "Confirm Project" in response.content.decode()
        assert business_unit.name in response.content.decode()
        assert selected_user.email in response.content.decode()

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
        session["project_user_add_selection"] = {"project_create_user_add": [selected_user.id]}
        session.save()

        response = client.post(reverse("projects:project_create_confirm"))

        project = Project.objects.get(name="Final Creation Project")
        assert response.status_code == 302
        assert response.url == reverse("projects:project_detail", args=[project.uuid])
        assert ProjectUserPermissions.objects.filter(
            project=project,
            user=selected_user,
            role="admin",
        ).exists()
        assert "project_create" not in client.session
        assert "project_user_add_selection" not in client.session

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
        session["project_user_add_selection"] = {"project_create_user_add": [selected_user.id]}
        session.save()

        client.post(reverse("projects:project_create_confirm"))

        project = Project.objects.get(name="History Test Project")
        for membership in ProjectUserPermissions.objects.filter(project=project):
            historical = membership.history.filter(history_type="+")
            assert historical.exists(), f"No creation history record for user {membership.user}"
            assert historical.first().history_user == user
