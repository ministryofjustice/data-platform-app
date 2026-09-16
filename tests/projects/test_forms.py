import uuid

import pytest
from model_bakery import baker

from projects.forms import ProjectMemberForm
from projects.models import ProjectPermission


@pytest.mark.django_db
class TestProjectMemberForm:
    def test_valid_selection_is_accepted(self, project):
        selected_oid = str(uuid.uuid4())
        data = {
            "oid": selected_oid,
            "email": "chosen.member@example.com",
            "display_name": "Chosen Member",
            "permissions": [ProjectPermission.MANAGE_API_KEYS],
        }

        form = ProjectMemberForm(data=data)

        assert form.is_valid()
        assert form.cleaned_data["oid"] == selected_oid
        assert form.cleaned_data["permissions"] == [ProjectPermission.MANAGE_API_KEYS]

    def test_permissions_are_optional(self, project):
        data = {
            "oid": str(uuid.uuid4()),
            "email": "chosen.member@example.com",
            "display_name": "Chosen Member",
        }

        form = ProjectMemberForm(data=data)

        assert form.is_valid()
        assert form.cleaned_data["permissions"] == []

    def test_missing_selection_is_rejected(self):
        form = ProjectMemberForm(data={"oid": "", "email": "", "display_name": ""})

        assert not form.is_valid()
        assert "Search for and select a project member" in form.errors["oid"]

    def test_canonicalises_oid_casing(self):
        selected_oid = uuid.uuid4()
        data = {"oid": str(selected_oid).upper(), "email": "a@example.com"}

        form = ProjectMemberForm(data=data)

        assert form.is_valid()
        assert form.cleaned_data["oid"] == str(selected_oid)

    def test_malformed_oid_is_rejected(self):
        form = ProjectMemberForm(data={"oid": "not-a-uuid", "email": "a@example.com"})

        assert not form.is_valid()
        assert "Enter a valid email address" in form.errors["oid"]

    def test_duplicate_in_session_is_rejected(self):
        selected_oid = str(uuid.uuid4())
        form = ProjectMemberForm(
            data={"oid": selected_oid, "email": "a@example.com"},
            existing_oids={selected_oid},
        )

        assert not form.is_valid()
        assert "This person has already been added" in form.errors["oid"]

    def test_editing_oid_is_exempt_from_duplicate_check(self):
        selected_oid = str(uuid.uuid4())
        form = ProjectMemberForm(
            data={"oid": selected_oid, "email": "a@example.com"},
            existing_oids={selected_oid},
            editing_oid=selected_oid,
        )

        assert form.is_valid()

    def test_existing_member_is_rejected(self, project):
        existing_member = baker.make("users.User", email="already.member@example.com")
        baker.make("projects.ProjectMembership", project=project, user=existing_member)

        form = ProjectMemberForm(
            data={"oid": str(existing_member.oid), "email": existing_member.email},
            project=project,
        )

        assert not form.is_valid()
        assert "This person is already a member of this project" in form.errors["oid"]
