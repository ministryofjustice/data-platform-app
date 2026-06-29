import pytest
from django.urls import reverse

from projects.views import BUSINESS_UNITS, PROJECT_JOURNEY_ID_SESSION_KEY


@pytest.fixture(autouse=True)
def authenticated_client(client, user):
    """Authenticate the client for project view tests."""
    client.force_login(user)


class TestCreateProjectView:
    pytestmark = pytest.mark.django_db

    def test_create_project_page_renders(self, client):
        response = client.get(reverse("projects:create_project"))

        assert response.status_code == 200
        assert "projects/create.html" in [t.name for t in response.templates]

    def test_context_contains_expected_business_units(self, client):
        response = client.get(reverse("projects:create_project"))

        assert response.context["business_units"] == sorted(BUSINESS_UNITS)

    @pytest.mark.parametrize("business_unit", BUSINESS_UNITS)
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

    def test_post_sets_journey_id_in_session(self, client):
        response = client.post(
            reverse("projects:create_project"),
            {
                "name": "My project",
                "business_unit": "HMPPS",
                "description": "A project description",
            },
        )

        assert response.status_code == 302
        journey_id = client.session[PROJECT_JOURNEY_ID_SESSION_KEY]

        assert journey_id

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

    def test_post_preserves_journey_id_across_add_members_steps(self, client):
        client.post(
            reverse("projects:create_project"),
            {
                "name": "Project One",
                "business_unit": "HMPPS",
                "description": "Description",
            },
        )
        journey_id = client.session[PROJECT_JOURNEY_ID_SESSION_KEY]

        response = client.post(
            reverse("projects:add_members"),
            {
                "add_members_now": "yes",
                "member_email": "person@example.com",
            },
        )

        assert response.status_code == 302
        assert client.session[PROJECT_JOURNEY_ID_SESSION_KEY] == journey_id

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

    def test_post_clears_journey_id_when_flow_completes(self, client):
        session = client.session
        session["project_data"] = {
            "name": "Project Blue Book",
            "business_unit": "HMPPS",
            "description": "Description text",
            "members": ["person@example.com"],
        }
        session[PROJECT_JOURNEY_ID_SESSION_KEY] = "journey-123"
        session.save()

        response = client.post(reverse("projects:check_details"))

        assert response.status_code == 302
        assert PROJECT_JOURNEY_ID_SESSION_KEY not in client.session
