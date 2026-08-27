import uuid

import pytest
from model_bakery import baker

from projects.forms import build_project_add_member_formset


def management_form(total_forms):
    return {
        "members-TOTAL_FORMS": str(total_forms),
        "members-INITIAL_FORMS": "0",
        "members-MIN_NUM_FORMS": "0",
        "members-MAX_NUM_FORMS": "1000",
    }


@pytest.mark.django_db
class TestProjectAddMemberFormSet:
    def test_valid_selection_collects_member(self, project):
        selected_oid = str(uuid.uuid4())
        data = management_form(1) | {
            "members-0-oid": selected_oid,
            "members-0-email": "chosen.member@example.com",
            "members-0-display_name": "Chosen Member",
        }

        formset = build_project_add_member_formset(project=project, data=data)

        assert formset.is_valid()
        assert formset.selected_members == [
            {
                "oid": selected_oid,
                "email": "chosen.member@example.com",
                "display_name": "Chosen Member",
            }
        ]

    def test_missing_selection_is_rejected(self, project):
        data = management_form(1) | {
            "members-0-oid": "",
            "members-0-email": "",
            "members-0-display_name": "",
        }

        formset = build_project_add_member_formset(project=project, data=data)

        assert not formset.is_valid()
        assert "Enter a valid email address" in formset.non_form_errors()

    def test_malformed_oid_is_rejected(self, project):
        data = management_form(1) | {
            "members-0-oid": "not-a-uuid",
            "members-0-email": "chosen.member@example.com",
            "members-0-display_name": "Chosen Member",
        }

        formset = build_project_add_member_formset(project=project, data=data)

        assert not formset.is_valid()
        assert "Enter a valid email address" in formset.non_form_errors()

    def test_duplicate_selection_is_deduplicated(self, project):
        selected_oid = str(uuid.uuid4())
        data = management_form(2) | {
            "members-0-oid": selected_oid,
            "members-0-email": "chosen.member@example.com",
            "members-0-display_name": "Chosen Member",
            "members-1-oid": selected_oid,
            "members-1-email": "chosen.member@example.com",
            "members-1-display_name": "Chosen Member",
        }

        formset = build_project_add_member_formset(project=project, data=data)

        assert formset.is_valid()
        assert formset.selected_members == [
            {
                "oid": selected_oid,
                "email": "chosen.member@example.com",
                "display_name": "Chosen Member",
            }
        ]

    def test_existing_member_is_rejected(self, project):
        existing_member = baker.make("users.User", email="already.member@example.com")
        baker.make(
            "projects.ProjectUserPermissions",
            project=project,
            user=existing_member,
            role="member",
        )
        data = management_form(1) | {
            "members-0-oid": str(existing_member.oid),
            "members-0-email": existing_member.email,
        }

        formset = build_project_add_member_formset(project=project, data=data)

        assert not formset.is_valid()
        assert (
            "One or more selected users are already members of this project."
            in formset.non_form_errors()
        )
