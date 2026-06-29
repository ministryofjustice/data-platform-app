import logging
from uuid import uuid4

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic.base import TemplateView

BUSINESS_UNITS = [
    "HMPPS",
    "OPG",
    "LAA",
    "Central Digital",
    "Technology Services",
    "HMCTS",
    "CICA",
    "OCTO",
    "YJB",
]


logger = logging.getLogger(__name__)
PROJECT_JOURNEY_ID_SESSION_KEY = "project_journey_id"


def get_project_journey_id(request):
    """Return the stable journey identifier for the project wizard."""
    journey_id = request.session.get(PROJECT_JOURNEY_ID_SESSION_KEY)
    if not journey_id:
        journey_id = uuid4().hex
        request.session[PROJECT_JOURNEY_ID_SESSION_KEY] = journey_id

    return journey_id


def clear_project_journey_id(request):
    """Remove the journey identifier when the wizard completes."""
    request.session.pop(PROJECT_JOURNEY_ID_SESSION_KEY, None)


class ListView(LoginRequiredMixin, TemplateView):
    template_name = "projects/list.html"


class CreateProjectView(LoginRequiredMixin, TemplateView):
    template_name = "projects/create.html"

    def get_context_data(self, **kwargs):
        """Add form data to context."""
        context = super().get_context_data(**kwargs)
        session_data = self.request.session.get("project_data", {})

        context["form_data"] = {
            "name": session_data.get("name", ""),
            "business_unit": session_data.get("business_unit", ""),
            "description": session_data.get("description", ""),
        }
        context["business_units"] = sorted(BUSINESS_UNITS)
        context["errors"] = {
            "name": "",
            "business_unit": "",
            "description": "",
        }
        return context

    def post(self, request, *args, **kwargs):
        """Handle form submission and store data in session."""
        journey_id = get_project_journey_id(request)
        name = request.POST.get("name", "").strip()
        business_unit = request.POST.get("business_unit", "").strip()
        description = request.POST.get("description", "").strip()

        # Basic validation
        errors = {}
        if not name:
            errors["name"] = "Enter a project name"
        if not business_unit:
            errors["business_unit"] = "Select a business unit"
        if not description:
            errors["description"] = "Enter a description"
        if business_unit and business_unit not in BUSINESS_UNITS:
            errors["business_unit"] = "Select a valid business unit"

        # If validation fails, re-render with errors
        if errors:
            logger.info(
                "project_flow.create.validation_failed user_id=%s journey_id=%s fields=%s",
                request.user.id,
                journey_id,
                ",".join(sorted(errors.keys())),
            )
            context = self.get_context_data(**kwargs)
            context["errors"] = errors
            context["form_data"] = {
                "name": name,
                "business_unit": business_unit,
                "description": description,
            }
            return self.render_to_response(context)

        # Store updated create-step fields while preserving existing session data
        # (for example members already added on the add-members step)
        existing_project_data = request.session.get("project_data", {})
        request.session["project_data"] = {
            **existing_project_data,
            "name": name,
            "business_unit": business_unit,
            "description": description,
        }

        logger.info(
            (
                "project_flow.create.saved user_id=%s journey_id=%s "
                "business_unit=%s members_count=%s"
            ),
            request.user.id,
            journey_id,
            business_unit,
            len(request.session["project_data"].get("members", [])),
        )

        return redirect(reverse("projects:add_members"))


class AddMembersView(LoginRequiredMixin, TemplateView):
    template_name = "projects/add_members.html"

    def get_context_data(self, **kwargs):
        """Add project and form data from session to context."""
        context = super().get_context_data(**kwargs)
        context["project_data"] = self.request.session.get("project_data", {})
        context["form_data"] = {
            "add_members_now": "",
            "member_email": "",
        }
        context["errors"] = {
            "add_members_now": "",
            "member_email": "",
        }
        return context

    def post(self, request, *args, **kwargs):
        """Handle add-members decision and optional member email."""
        journey_id = get_project_journey_id(request)
        action = request.POST.get("action", "continue").strip()
        add_members_now = request.POST.get("add_members_now", "").strip()
        member_email = request.POST.get("member_email", "").strip()

        if action not in {"add_another", "continue"}:
            action = "continue"

        errors = {}

        if add_members_now not in {"yes", "no"}:
            errors["add_members_now"] = "Choose Yes or No"
        elif action == "add_another" and add_members_now != "yes":
            errors["add_members_now"] = "Select Yes to add another member"

        if add_members_now == "yes":
            if not member_email:
                errors["member_email"] = "Enter a valid email address"
            else:
                try:
                    validate_email(member_email)
                except ValidationError:
                    errors["member_email"] = "Enter a valid email address"

        if errors:
            logger.info(
                (
                    "project_flow.add_members.validation_failed user_id=%s "
                    "journey_id=%s action=%s add_members_now=%s fields=%s"
                ),
                request.user.id,
                journey_id,
                action,
                add_members_now or "unset",
                ",".join(sorted(errors.keys())),
            )
            context = self.get_context_data(**kwargs)
            context["errors"] = errors
            context["form_data"] = {
                "add_members_now": add_members_now,
                "member_email": member_email,
            }
            return self.render_to_response(context)

        project_data = request.session.get("project_data", {})
        members = project_data.get("members", [])

        if add_members_now == "yes":
            members_lower = {m.casefold() for m in members}
            if member_email.casefold() in members_lower:
                errors["member_email"] = "This member has already been added"
                logger.info(
                    (
                        "project_flow.add_members.duplicate_rejected user_id=%s "
                        "journey_id=%s members_count=%s"
                    ),
                    request.user.id,
                    journey_id,
                    len(members),
                )
                context = self.get_context_data(**kwargs)
                context["errors"] = errors
                context["form_data"] = {
                    "add_members_now": add_members_now,
                    "member_email": member_email,
                }
                return self.render_to_response(context)

            if len(members) >= 20:
                errors["member_email"] = "You can only add up to 20 members"
                logger.info(
                    (
                        "project_flow.add_members.limit_rejected user_id=%s "
                        "journey_id=%s members_count=%s"
                    ),
                    request.user.id,
                    journey_id,
                    len(members),
                )
                context = self.get_context_data(**kwargs)
                context["errors"] = errors
                context["form_data"] = {
                    "add_members_now": add_members_now,
                    "member_email": member_email,
                }
                return self.render_to_response(context)

            members.append(member_email)
            logger.info(
                (
                    "project_flow.add_members.member_added user_id=%s "
                    "journey_id=%s members_count=%s"
                ),
                request.user.id,
                journey_id,
                len(members),
            )

        project_data["members"] = members
        request.session["project_data"] = project_data

        if action == "add_another":
            logger.info(
                ("project_flow.add_members.add_another user_id=%s journey_id=%s members_count=%s"),
                request.user.id,
                journey_id,
                len(members),
            )
            context = self.get_context_data(**kwargs)
            context["form_data"] = {
                "add_members_now": "yes",
                "member_email": "",
            }
            return self.render_to_response(context)

        logger.info(
            ("project_flow.add_members.continue user_id=%s journey_id=%s members_count=%s"),
            request.user.id,
            journey_id,
            len(members),
        )

        return redirect(reverse("projects:check_details"))


class CheckDetailsView(LoginRequiredMixin, TemplateView):
    template_name = "projects/check_details.html"

    def get_context_data(self, **kwargs):
        """Add project data from session to context."""
        context = super().get_context_data(**kwargs)
        context["project_data"] = self.request.session.get("project_data", {})
        return context

    def post(self, request, *args, **kwargs):
        """Handle final project creation."""
        journey_id = get_project_journey_id(request)
        project_data = request.session.get("project_data", {})
        logger.info(
            ("project_flow.check_details.submitted user_id=%s journey_id=%s members_count=%s"),
            request.user.id,
            journey_id,
            len(project_data.get("members", [])),
        )

        # TODO: Implement actual project creation logic and show stuff
        # For the moment just clear session and redirect to list (maybe?)
        request.session.pop("project_data", None)
        clear_project_journey_id(request)

        logger.info(
            "project_flow.check_details.session_cleared user_id=%s journey_id=%s",
            request.user.id,
            journey_id,
        )
        return redirect(reverse("projects:projects_list"))
