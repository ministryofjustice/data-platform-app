import pytest
from django.urls import reverse
from model_bakery import baker

from projects.models import Project, ProjectUserPermissions


@pytest.fixture
def project(db, user):
    """A project created by a user."""

    project = baker.make(
        "projects.Project", name="Example Project", slug="example-slug", created_by=user
    )

    baker.make("projects.ProjectUserPermissions", project=project, user=user, role="admin")

    return project


class TestListView:
    """Tests for the ProjectListView at '/projects/'."""

    def test_list_page_renders(self, client, user):
        client.force_login(user)
        response = client.get(reverse("projects:projects_list"))

        assert response.status_code == 200
        assert "projects/list.html" in [t.name for t in response.templates]


class TestDetailView:
    """Tests for the ProjectDetailView at '/projects/<slug>/'."""

    def test_detail_page_renders(self, client, user, project):
        client.force_login(user)
        response = client.get(reverse("projects:project_detail", args=[project.slug]))

        assert response.status_code == 200
        assert "projects/detail.html" in [t.name for t in response.templates]


class TestProjectDeleteView:
    """Tests for the ProjectDeleteView at '/projects/<slug>/delete'."""

    def test_delete_page_renders(self, client, user, project):
        client.force_login(user)
        response = client.get(reverse("projects:project_delete", args=[project.slug]))

        assert response.status_code == 200
        assert "projects/delete-confirm.html" in [t.name for t in response.templates]

    def test_delete_project(self, client, user, project):
        client.force_login(user)
        response = client.post(reverse("projects:project_delete", args=[project.slug]))

        assert response.status_code == 302
        assert not Project.objects.filter(id=project.id).exists()


class TestProjectRemoveUserView:
    """Tests for the ProjectRemoveUserView at '/projects/<slug>/users/<user_id>/remove/'."""

    def test_remove_user_page_renders(self, client, user, project):
        client.force_login(user)
        response = client.get(
            reverse("projects:project_user_remove", args=[project.slug, user.id])
        )

        assert response.status_code == 200
        assert "projects/user-remove-confirm.html" in [t.name for t in response.templates]

    def test_remove_user(self, client, user, project):
        client.force_login(user)
        response = client.post(
            reverse("projects:project_user_remove", args=[project.slug, user.id])
        )

        assert response.status_code == 302
        assert not ProjectUserPermissions.objects.filter(project=project, user=user).exists()


class TestProjectAddUsersFlow:
    """Tests for the ProjectAddUsersView and ProjectAddUsersConfirmView."""

    def test_add_users_page_renders(self, client, user, project):
        client.force_login(user)

        response = client.get(reverse("projects:project_users_add", args=[project.slug]))

        assert response.status_code == 200
        assert "projects/user-add.html" in [t.name for t in response.templates]

    def test_add_users_page_context_contains_formset(self, client, user, project):
        client.force_login(user)

        response = client.get(reverse("projects:project_users_add", args=[project.slug]))

        assert response.status_code == 200
        assert "formset" in response.context

    def test_add_users_page_repopulates_selected_users_from_session(self, client, user, project):
        selected_user_one = baker.make("users.User", email="member.five@example.com")
        selected_user_two = baker.make("users.User", email="member.six@example.com")
        client.force_login(user)

        session = client.session
        session["project_user_add_selection"] = {
            str(project.id): [selected_user_one.id, selected_user_two.id]
        }
        session.save()

        response = client.get(reverse("projects:project_users_add", args=[project.slug]))

        assert response.status_code == 200
        formset = response.context["formset"]
        assert formset.total_form_count() == 2
        assert formset.forms[0].initial["user"] == selected_user_one.id
        assert formset.forms[1].initial["user"] == selected_user_two.id

    def test_add_users_page_submits_and_redirects_to_confirm(self, client, user, project):

        user_to_add = baker.make("users.User", email="member.one@example.com")
        client.force_login(user)

        response = client.post(
            reverse("projects:project_users_add", args=[project.slug]),
            data={
                "members-TOTAL_FORMS": "1",
                "members-INITIAL_FORMS": "0",
                "members-MIN_NUM_FORMS": "0",
                "members-MAX_NUM_FORMS": "1000",
                "members-0-user": str(user_to_add.id),
            },
        )

        assert response.status_code == 302
        assert response.url == reverse("projects:project_users_add_confirm", args=[project.slug])

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
        response = client.get(reverse("projects:project_users_add", args=[project.slug]))

        content = response.content.decode()
        assert response.status_code == 200
        assert "new.member@example.com" in content
        assert "already.member@example.com" not in content

    def test_add_users_page_rejects_duplicate_user_submission(self, client, user, project):

        user_to_add = baker.make("users.User", email="member.two@example.com")
        client.force_login(user)

        response = client.post(
            reverse("projects:project_users_add", args=[project.slug]),
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
        session["project_user_add_selection"] = {str(project.id): [selected_user.id]}
        session.save()

        response = client.get(reverse("projects:project_users_add_confirm", args=[project.slug]))

        assert response.status_code == 200
        assert "projects/user-add-confirm.html" in [t.name for t in response.templates]
        assert selected_user.email in response.content.decode()

    def test_confirm_adds_users_to_project(self, client, user, project):

        selected_user = baker.make("users.User", email="member.four@example.com")
        client.force_login(user)
        session = client.session
        session["project_user_add_selection"] = {str(project.id): [selected_user.id]}
        session.save()

        response = client.post(reverse("projects:project_users_add_confirm", args=[project.slug]))

        assert response.status_code == 302
        assert response.url == reverse("projects:project_users", args=[project.slug])
        assert ProjectUserPermissions.objects.filter(
            project=project,
            user=selected_user,
            role="admin",
        ).exists()
