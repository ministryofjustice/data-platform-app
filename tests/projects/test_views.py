import pytest
from django.urls import reverse

from projects.models import BusinessUnit, Project, ProjectMember
from users.models import User


@pytest.fixture(autouse=True)
def authenticated_client(client, user):
    """Authenticate the client for project view tests."""
    client.force_login(user)


class TestCreateProjectView:
    pytestmark = pytest.mark.django_db

    def test_cancel_clears_project_data(self, client):
        session = client.session
        session["project_data"] = {
            "name": "Draft Project",
            "business_unit": "HMPPS",
            "description": "Draft description",
            "members": ["person@example.com"],
        }
        session.save()

        response = client.get(reverse("projects:cancel_create"))

        assert response.status_code == 302
        assert response.url == reverse("projects:projects_list")
        assert "project_data" not in client.session

    def test_create_project_page_renders(self, client):
        response = client.get(reverse("projects:create_project"))

        assert response.status_code == 200
        assert "projects/create.html" in [t.name for t in response.templates]

    def test_context_contains_expected_business_units(self, client):
        response = client.get(reverse("projects:create_project"))
        expected_business_units = list(
            BusinessUnit.objects.order_by("name").values_list("name", flat=True)
        )

        assert response.context["business_units"] == expected_business_units

    @pytest.mark.parametrize(
        "business_unit",
        [
            "CICA",
            "Central Digital",
            "HMCTS",
            "HMPPS",
            "LAA",
            "OCTO",
            "OPG",
            "Technology Services",
            "YJB",
        ],
    )
    def test_post_with_allowed_business_unit_redirects(self, client, business_unit):
        response = client.post(
            reverse("projects:create_project"),
            {
                "name": "My project",
                "business_unit": business_unit,
                "description": "A project description",
            },
        )

        assert response.status_code == 302
        assert response.url == reverse("projects:add_members")

    def test_post_does_not_require_journey_id_in_session(self, client):
        response = client.post(
            reverse("projects:create_project"),
            {
                "name": "My project",
                "business_unit": "HMPPS",
                "description": "A project description",
            },
        )

        assert response.status_code == 302
        assert response.url == reverse("projects:add_members")

    def test_post_with_invalid_business_unit_shows_error(self, client):
        response = client.post(
            reverse("projects:create_project"),
            {
                "name": "My project",
                "business_unit": "Invalid unit",
                "description": "A project description",
            },
        )

        assert response.status_code == 200
        assert "Select a valid business unit" in response.content.decode()

    def test_post_preserves_existing_members_in_session(self, client):
        session = client.session
        session["project_data"] = {
            "name": "Existing name",
            "business_unit": "HMPPS",
            "description": "Existing description",
            "members": ["member.one@example.com"],
        }
        session.save()

        response = client.post(
            reverse("projects:create_project"),
            {
                "name": "Updated name",
                "business_unit": "OPG",
                "description": "Updated description",
            },
        )

        assert response.status_code == 302
        assert response.url == reverse("projects:add_members")
        assert client.session["project_data"]["members"] == ["member.one@example.com"]


class TestAddMembersView:
    pytestmark = pytest.mark.django_db

    def test_get_prefills_yes_when_members_exist_in_session(self, client):
        session = client.session
        session["project_data"] = {
            "name": "Project One",
            "business_unit": "HMPPS",
            "description": "Description",
            "members": ["person@example.com"],
        }
        session.save()

        response = client.get(reverse("projects:add_members"))

        assert response.status_code == 200
        assert response.context["form_data"]["add_members_now"] == "yes"

    def test_add_members_page_renders(self, client):
        response = client.get(reverse("projects:add_members"))

        assert response.status_code == 200
        assert "projects/add_members.html" in [t.name for t in response.templates]
        body = response.content.decode()
        assert "Add Members" in body
        assert "Do you want to add project members now?" in body
        assert "You can also add members later" in body

    def test_post_requires_yes_or_no_selection(self, client):
        response = client.post(reverse("projects:add_members"), {})

        assert response.status_code == 200
        assert "Choose Yes or No" in response.content.decode()

    def test_post_yes_requires_email(self, client):
        response = client.post(
            reverse("projects:add_members"),
            {
                "add_members_now": "yes",
                "member_email": "",
            },
        )

        assert response.status_code == 200
        assert "Enter an email address" in response.content.decode()

    def test_post_yes_requires_valid_email_format(self, client):
        response = client.post(
            reverse("projects:add_members"),
            {
                "add_members_now": "yes",
                "member_email": "not-an-email",
            },
        )

        assert response.status_code == 200
        assert "Enter a valid email address" in response.content.decode()

    def test_post_no_redirects_to_check_details_without_adding_members(self, client):
        session = client.session
        session["project_data"] = {
            "name": "Project One",
            "business_unit": "HMPPS",
            "description": "Description",
        }
        session.save()

        response = client.post(
            reverse("projects:add_members"),
            {
                "add_members_now": "no",
            },
        )

        assert response.status_code == 302
        assert response.url == reverse("projects:check_details")
        assert client.session["project_data"].get("members", []) == []

    def test_post_preserves_members_across_add_members_steps(self, client):
        client.post(
            reverse("projects:create_project"),
            {
                "name": "Project One",
                "business_unit": "HMPPS",
                "description": "Description",
            },
        )

        response = client.post(
            reverse("projects:add_members"),
            {
                "add_members_now": "yes",
                "member_email": "person@example.com",
            },
        )

        assert response.status_code == 302
        assert client.session["project_data"]["members"] == ["person@example.com"]

    def test_post_yes_adds_member_and_redirects(self, client):
        session = client.session
        session["project_data"] = {
            "name": "Project One",
            "business_unit": "HMPPS",
            "description": "Description",
            "members": [],
        }
        session.save()

        response = client.post(
            reverse("projects:add_members"),
            {
                "add_members_now": "yes",
                "member_email": "person@example.com",
            },
        )

        assert response.status_code == 302
        assert response.url == reverse("projects:check_details")
        assert client.session["project_data"]["members"] == ["person@example.com"]

    def test_post_add_another_adds_member_and_stays_on_page(self, client):
        session = client.session
        session["project_data"] = {
            "name": "Project One",
            "business_unit": "HMPPS",
            "description": "Description",
            "members": [],
        }
        session.save()

        response = client.post(
            reverse("projects:add_members"),
            {
                "action": "add_another",
                "add_members_now": "yes",
                "member_email": "person@example.com",
            },
        )

        assert response.status_code == 200
        assert "projects/add_members.html" in [t.name for t in response.templates]
        assert client.session["project_data"]["members"] == ["person@example.com"]

    def test_post_add_another_requires_yes_selection(self, client):
        response = client.post(
            reverse("projects:add_members"),
            {
                "action": "add_another",
                "add_members_now": "no",
                "member_email": "person@example.com",
            },
        )

        assert response.status_code == 200
        assert "Select Yes to add another member" in response.content.decode()


class TestCheckDetailsView:
    pytestmark = pytest.mark.django_db

    def test_check_details_page_renders_with_project_data(self, client):
        session = client.session
        session["project_data"] = {
            "name": "Project Blue Book",
            "business_unit": "HMPPS",
            "description": "Description text",
            "members": ["person@example.com"],
        }
        session.save()

        response = client.get(reverse("projects:check_details"))

        assert response.status_code == 200
        assert "Project Blue Book" in response.content.decode()
        assert "HMPPS" in response.content.decode()
        assert "Description text" in response.content.decode()
        assert "person@example.com" in response.content.decode()

    def test_post_clears_project_data_when_flow_completes(self, client):
        existing_member = User.objects.create_user(
            username="existing.member",
            email="existing.member@example.com",
            password="unsafe-test-password",
        )

        session = client.session
        session["project_data"] = {
            "name": "Project Blue Book",
            "business_unit": "HMPPS",
            "description": "Description text",
            "members": ["existing.member@example.com", "new.member@example.com"],
        }
        session.save()

        response = client.post(reverse("projects:check_details"))

        assert response.status_code == 302
        assert "project_data" not in client.session

        project = Project.objects.get(name="Project Blue Book")
        business_unit = BusinessUnit.objects.get(name="HMPPS")

        assert project.business_unit == business_unit
        assert project.description == "Description text"

        members = ProjectMember.objects.filter(project=project)
        assert members.count() == 2
        assert members.filter(email="existing.member@example.com", user=existing_member).exists()
        assert members.filter(email="new.member@example.com", user__isnull=True).exists()
