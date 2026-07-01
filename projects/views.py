from uuid import uuid4

import structlog
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.text import slugify
from django.views.generic.base import TemplateView

from projects.forms import ProjectCreateForm
from projects.models import BusinessUnit, Project, ProjectMember
from users.models import User

logger = structlog.get_logger(__name__)
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


def _unique_project_slug(name: str) -> str:
    """Generate a unique slug for a project based on its name."""
    base = slugify(name)[:40] or "project"
    slug = base
    suffix = 2
    while Project.objects.filter(slug=slug).exists():
        slug = f"{base}-{suffix}"
        suffix += 1
    return slug


def _business_unit_code(name: str) -> str:
    """Generate a code for a business unit based on its name."""
    return slugify(name).replace("-", "_")[:20] or "unknown"


class ListView(LoginRequiredMixin, TemplateView):
    template_name = "projects/list.html"


class CreateProjectView(LoginRequiredMixin, TemplateView):
    template_name = "projects/create.html"

    def _build_context(self, form: ProjectCreateForm) -> dict:
        """Build template context from a bound or unbound form."""
        business_units = [
            choice[0] for choice in form.fields["business_unit"].choices if choice[0]
        ]
        return {
            "form_data": {
                "name": form["name"].value() or "",
                "business_unit": form["business_unit"].value() or "",
                "description": form["description"].value() or "",
            },
            "business_units": business_units,
            "errors": {
                "name": form.errors.get("name", [""])[0],
                "business_unit": form.errors.get("business_unit", [""])[0],
                "description": form.errors.get("description", [""])[0],
            },
        }

    def get_context_data(self, **kwargs):
        """Populate form fields from session data when the page is loaded."""
        context = super().get_context_data(**kwargs)
        session_data = self.request.session.get("project_data", {})
        form = ProjectCreateForm(initial=session_data)
        context.update(self._build_context(form))
        return context

    def post(self, request, *args, **kwargs):
        """Validate via ProjectCreateForm and store clean data in session."""
        journey_id = get_project_journey_id(request)
        form = ProjectCreateForm(request.POST)

        if not form.is_valid():
            # form.errors already contains the declared error messages
            logger.info(
                "project_flow.create.validation_failed",
                user_id=request.user.id,
                journey_id=journey_id,
                fields=sorted(form.errors.keys()),
            )
            context = super().get_context_data(**kwargs)
            context.update(self._build_context(form))
            return self.render_to_response(context)

        # Store validated data, preserving any members added on a previous visit
        existing_project_data = request.session.get("project_data", {})
        request.session["project_data"] = {
            **existing_project_data,
            "name": form.cleaned_data["name"],
            "business_unit": form.cleaned_data["business_unit"],
            "description": form.cleaned_data["description"],
        }

        logger.info(
            "project_flow.create.saved",
            user_id=request.user.id,
            journey_id=journey_id,
            business_unit=form.cleaned_data["business_unit"],
            members_count=len(request.session["project_data"].get("members", [])),
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
                "project_flow.add_members.validation_failed",
                user_id=request.user.id,
                journey_id=journey_id,
                action=action,
                add_members_now=add_members_now or "unset",
                fields=sorted(errors.keys()),
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
                    "project_flow.add_members.duplicate_rejected",
                    user_id=request.user.id,
                    journey_id=journey_id,
                    members_count=len(members),
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
                    "project_flow.add_members.limit_rejected",
                    user_id=request.user.id,
                    journey_id=journey_id,
                    members_count=len(members),
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
                "project_flow.add_members.member_added",
                user_id=request.user.id,
                journey_id=journey_id,
                members_count=len(members),
            )

        project_data["members"] = members
        request.session["project_data"] = project_data

        if action == "add_another":
            logger.info(
                "project_flow.add_members.add_another",
                user_id=request.user.id,
                journey_id=journey_id,
                members_count=len(members),
            )
            context = self.get_context_data(**kwargs)
            context["form_data"] = {
                "add_members_now": "yes",
                "member_email": "",
            }
            return self.render_to_response(context)

        logger.info(
            "project_flow.add_members.continue",
            user_id=request.user.id,
            journey_id=journey_id,
            members_count=len(members),
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

        name = project_data.get("name", "").strip()
        business_unit_name = project_data.get("business_unit", "").strip()
        description = project_data.get("description", "").strip()
        member_emails = project_data.get("members", [])

        if not name or not business_unit_name or not description:
            logger.error(
                "project_flow.check_details.missing_data",
                user_id=request.user.id,
                journey_id=journey_id,
                name_present=bool(name),
                business_unit_present=bool(business_unit_name),
                description_present=bool(description),
            )
            return redirect(reverse("projects:create_project"))

        with transaction.atomic():
            business_unit, _ = BusinessUnit.objects.get_or_create(
                name=business_unit_name,
                defaults={"code": _business_unit_code(business_unit_name)},
            )

            project = Project.objects.create(
                name=name,
                description=description,
                slug=_unique_project_slug(name),
                business_unit=business_unit,
                created_by=request.user,
            )

            member_rows = []
            linked_member_count = 0
            for email in member_emails:
                existing_user = User.objects.filter(email__iexact=email).first()
                if existing_user:
                    linked_member_count += 1

                member_rows.append(ProjectMember(project=project, email=email, user=existing_user))

            if member_rows:
                ProjectMember.objects.bulk_create(member_rows)

        logger.info(
            "project_flow.check_details.project_created",
            user_id=request.user.id,
            journey_id=journey_id,
            project_id=project.id,
            members_count=len(member_emails),
            linked_members_count=linked_member_count,
        )

        request.session.pop("project_data", None)
        clear_project_journey_id(request)

        logger.info(
            "project_flow.check_details.session_cleared",
            user_id=request.user.id,
            journey_id=journey_id,
        )
        return redirect(reverse("projects:projects_list"))
