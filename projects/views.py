import structlog
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.text import slugify
from django.views.generic.base import TemplateView, View
from django.views.generic.edit import CreateView

from projects.forms import AddMembersForm, ProjectCreateForm
from projects.models import BusinessUnit, Project, ProjectMember
from users.models import User

logger = structlog.get_logger(__name__)


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


class CancelProjectCreationView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        """Clear in-progress project flow session state and return to list."""
        had_project_data = "project_data" in request.session

        request.session.pop("project_data", None)

        logger.info(
            "project_flow.cancelled",
            user_id=request.user.id,
            had_project_data=had_project_data,
        )

        return redirect(reverse("projects:projects_list"))


class CreateProjectView(LoginRequiredMixin, CreateView):
    template_name = "projects/create.html"
    form_class = ProjectCreateForm

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
        form = context["form"]
        context.update(self._build_context(form))
        return context

    def get_initial(self):
        """Pre-populate the form from any in-progress session data."""
        return self.request.session.get("project_data", {})

    def get_form_kwargs(self):
        """
        Remove the instance kwarg that CreateView adds,
        since this is a plain Form not ModelForm.
        """
        kwargs = super().get_form_kwargs()
        kwargs.pop("instance", None)
        return kwargs

    def form_invalid(self, form):
        """Log failed validation and re-render the current step."""
        logger.info(
            "project_flow.create.validation_failed",
            user_id=self.request.user.id,
            fields=sorted(form.errors.keys()),
        )
        return self.render_to_response(self.get_context_data(form=form))

    def form_valid(self, form):
        """Store validated form data in session and continue the wizard."""
        # Store validated data, preserving any members added on a previous visit
        existing_project_data = self.request.session.get("project_data", {})
        self.request.session["project_data"] = {
            **existing_project_data,
            "name": form.cleaned_data["name"],
            "business_unit": form.cleaned_data["business_unit"],
            "description": form.cleaned_data["description"],
        }

        logger.info(
            "project_flow.create.saved",
            user_id=self.request.user.id,
            business_unit=form.cleaned_data["business_unit"],
            members_count=len(self.request.session["project_data"].get("members", [])),
        )

        return redirect(reverse("projects:add_members"))


class AddMembersView(LoginRequiredMixin, TemplateView):
    template_name = "projects/add_members.html"

    def get_context_data(self, **kwargs):
        """Add project and form data from session to context."""
        context = super().get_context_data(**kwargs)
        project_data = self.request.session.get("project_data", {})
        members = project_data.get("members", [])

        context["project_data"] = project_data
        context["form_data"] = {
            "add_members_now": "yes" if members else "",
            "member_email": "",
        }
        context["errors"] = {
            "add_members_now": "",
            "member_email": "",
        }
        return context

    def post(self, request, *args, **kwargs):
        """Handle add-members decision and optional member email."""
        project_data = request.session.get("project_data", {})
        members = project_data.get("members", [])

        form = AddMembersForm(request.POST, existing_members=members)

        if not form.is_valid():
            logger.info(
                "project_flow.add_members.validation_failed",
                user_id=request.user.id,
                action=request.POST.get("action") or "continue",
                add_members_now=request.POST.get("add_members_now") or "unset",
                fields=sorted(form.errors.keys()),
            )
            context = self.get_context_data(**kwargs)
            context["errors"] = {
                "add_members_now": form.errors.get("add_members_now", [""])[0],
                "member_email": form.errors.get("member_email", [""])[0],
            }
            context["form_data"] = {
                "add_members_now": request.POST.get("add_members_now", ""),
                "member_email": request.POST.get("member_email", ""),
            }
            return self.render_to_response(context)

        add_members_now = form.cleaned_data["add_members_now"]
        member_email = form.cleaned_data.get("member_email", "")
        action = form.cleaned_data["action"]

        if add_members_now == "yes":
            members.append(member_email)
            logger.info(
                "project_flow.add_members.member_added",
                user_id=request.user.id,
                members_count=len(members),
            )

        project_data["members"] = members
        request.session["project_data"] = project_data

        if action == "add_another":
            logger.info(
                "project_flow.add_members.add_another",
                user_id=request.user.id,
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
            members_count=len(members),
        )

        return redirect(reverse("projects:check_details"))


def _get_complete_project_data(session: dict) -> dict | None:
    """Return validated project data from the session, or None if required fields are missing."""
    data = session.get("project_data", {})
    if data.get("name") and data.get("business_unit") and data.get("description"):
        return data
    return None


class CheckDetailsView(LoginRequiredMixin, TemplateView):
    template_name = "projects/check_details.html"

    def get_context_data(self, **kwargs):
        """Add project data from session to context."""
        context = super().get_context_data(**kwargs)
        context["project_data"] = self.request.session.get("project_data", {})
        return context

    def post(self, request, *args, **kwargs):
        """Handle final project creation."""
        project_data = _get_complete_project_data(request.session)

        if project_data is None:
            logger.error(
                "project_flow.check_details.missing_data",
                user_id=request.user.id,
            )
            return redirect(reverse("projects:create_project"))

        name = project_data["name"].strip()
        business_unit_name = project_data["business_unit"].strip()
        description = project_data["description"].strip()
        member_emails = project_data.get("members", [])

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
            project_id=project.id,
            members_count=len(member_emails),
            linked_members_count=linked_member_count,
        )

        request.session.pop("project_data", None)

        logger.info(
            "project_flow.check_details.session_cleared",
            user_id=request.user.id,
        )
        return redirect(reverse("projects:projects_list"))
