from django.db import transaction
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.urls.base import reverse_lazy
from django.utils.text import slugify
from django.views.generic.base import View
from django.views.generic.detail import DetailView
from django.views.generic.edit import DeleteView, FormView
from django.views.generic.list import ListView

from projects.forms import (
    ProjectCreateAddUsersDecisionForm,
    ProjectCreateForm,
    build_project_add_member_formset,
)
from projects.models import BusinessUnit, Project, ProjectUserPermissions
from users.models import User

ADD_USER_SESSION_KEY = "project_user_add_selection"
PROJECT_CREATE_SESSION_KEY = "project_create"
USER_BUCKET_SESSION_KEY = "project_create_user_add"


def clear_project_create_session(request):
    request.session.pop(PROJECT_CREATE_SESSION_KEY, None)
    request.session.pop(ADD_USER_SESSION_KEY, None)


class ProjectUserSelectionSessionMixin:
    def get_project(self):
        return None

    def get_user_bucket_key(self):
        raise NotImplementedError

    def get_selected_user_ids(self):
        session_map = self.request.session.get(ADD_USER_SESSION_KEY, {})
        return [int(user_id) for user_id in session_map.get(self.get_user_bucket_key(), [])]

    def set_selected_user_ids(self, user_ids):
        session_map = self.request.session.get(ADD_USER_SESSION_KEY, {})
        session_map[self.get_user_bucket_key()] = list(user_ids)
        self.request.session[ADD_USER_SESSION_KEY] = session_map

    def clear_selected_user_ids(self):
        session_map = self.request.session.get(ADD_USER_SESSION_KEY, {})
        session_map.pop(self.get_user_bucket_key(), None)
        self.request.session[ADD_USER_SESSION_KEY] = session_map


class ExistingProjectMixin:
    def get_project(self):
        if not hasattr(self, "_project"):
            self._project = get_object_or_404(
                Project.objects.filter(
                    user_permissions__user=self.request.user,
                    user_permissions__role="admin",
                ).distinct(),
                slug=self.kwargs["slug"],
            )
        return self._project

    def get_user_bucket_key(self):
        return f"project:{self.get_project().id}"


class ProjectListView(ListView):
    template_name = "projects/list.html"
    context_object_name = "user_projects"
    model = Project

    def get_queryset(self):
        """
        set PK to whatever user you've created in db.
        Code will be deleted once user auth is implemented
        """
        return self.request.user.projects.distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        clear_project_create_session(self.request)
        context["success_message"] = self.request.session.pop("success_message", None)
        return context


class ProjectDetailView(DetailView):
    template_name = "projects/detail.html"
    context_object_name = "project"
    model = Project

    def get_queryset(self):
        return (
            Project.objects.filter(user_permissions__user=self.request.user)
            .select_related("business_unit", "created_by")
            .prefetch_related("users", "user_permissions__user")
            .distinct()
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["success_message"] = self.request.session.pop("success_message", None)
        return context


class ProjectCreateView(FormView):
    template_name = "projects/create.html"
    form_class = ProjectCreateForm

    def get_initial(self):
        project_data = self.request.session.get(PROJECT_CREATE_SESSION_KEY, {})
        return {
            "name": project_data.get("name", ""),
            "description": project_data.get("description", ""),
            "business_unit": project_data.get("business_unit_id"),
        }

    def form_valid(self, form):
        cleaned = form.cleaned_data
        self.request.session[PROJECT_CREATE_SESSION_KEY] = {
            "name": cleaned["name"],
            "description": cleaned["description"],
            "business_unit_id": cleaned["business_unit"].id,
        }
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse("projects:project_create_add_users")


class ProjectUserSelectionFormView(ProjectUserSelectionSessionMixin, FormView):
    template_name = "projects/user-add.html"

    def get_success_url(self):
        raise NotImplementedError

    def get_form(self, form_class=None):
        data = self.request.POST if self.request.method == "POST" else None
        initial = None
        extra = 1

        if self.request.method == "GET":
            selected_user_ids = self.get_selected_user_ids()
            if selected_user_ids:
                initial = [{"user": user_id} for user_id in selected_user_ids]
                extra = 0

        return build_project_add_member_formset(
            project=self.get_project(),
            data=data,
            initial=initial,
            extra=extra,
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["formset"] = context["form"]
        context["project"] = self.get_project()
        return context

    def form_valid(self, form):
        self.set_selected_user_ids(form.selected_user_ids)
        return redirect(self.get_success_url())


class ProjectCreateAddUsersView(ProjectUserSelectionFormView):
    template_name = "projects/create-user-add.html"

    def get_user_bucket_key(self):
        return USER_BUCKET_SESSION_KEY

    def get_success_url(self):
        return reverse("projects:project_create_confirm")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["project"] = self.request.session.get(PROJECT_CREATE_SESSION_KEY, {})
        context.setdefault("decision_form", self.get_decision_form())
        return context

    def get_decision_form(self):
        data = self.request.POST if self.request.method == "POST" else None
        initial = None
        if self.request.method == "GET" and self.get_selected_user_ids():
            initial = {"add_user": "yes"}
        return ProjectCreateAddUsersDecisionForm(data=data, initial=initial)

    def get_unbound_formset(self):
        initial = None
        extra = 1
        selected_user_ids = self.get_selected_user_ids()
        if selected_user_ids:
            initial = [{"user": user_id} for user_id in selected_user_ids]
            extra = 0

        return build_project_add_member_formset(
            project=self.get_project(),
            data=None,
            initial=initial,
            extra=extra,
        )

    def form_invalid(self, form):
        return self.render_to_response(
            self.get_context_data(form=form, decision_form=self.get_decision_form())
        )

    def post(self, request, *args, **kwargs):
        decision_form = self.get_decision_form()
        if not decision_form.is_valid():
            return self.render_to_response(
                self.get_context_data(
                    form=self.get_unbound_formset(),
                    decision_form=decision_form,
                )
            )

        if decision_form.cleaned_data["add_user"] == "no":
            self.clear_selected_user_ids()
            return redirect("projects:project_create_confirm")

        return super().post(request, *args, **kwargs)


class ProjectCreateConfirmView(ProjectUserSelectionSessionMixin, View):
    template_name = "projects/create-confirm.html"

    def get_user_bucket_key(self):
        return USER_BUCKET_SESSION_KEY

    def get_selected_users(self):
        selected_user_ids = self.get_selected_user_ids()
        return User.objects.filter(id__in=selected_user_ids).order_by("email")

    def get(self, request, *args, **kwargs):
        project_data = self.request.session.get(PROJECT_CREATE_SESSION_KEY, {})
        business_unit_id = project_data.get("business_unit_id")
        business_unit = get_object_or_404(BusinessUnit, pk=business_unit_id)
        selected_users = list(self.get_selected_users())

        context = {
            "project": project_data,
            "business_unit": business_unit,
            "selected_users": selected_users,
        }
        return render(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        project_data = self.request.session.get(PROJECT_CREATE_SESSION_KEY, {})
        with transaction.atomic():
            project = Project.objects.create(
                name=project_data["name"],
                description=project_data["description"],
                business_unit_id=project_data["business_unit_id"],
                created_by=self.request.user,
                slug=slugify(project_data["name"]),
            )
            selected_user_ids = self.get_selected_user_ids()

            # ensure the owner is included
            owner_user_id = self.request.user.id
            if owner_user_id not in selected_user_ids:
                selected_user_ids.append(owner_user_id)

            ProjectUserPermissions.objects.bulk_create(
                [
                    ProjectUserPermissions(
                        project=project,
                        user_id=user_id,
                        role="admin",
                    )
                    for user_id in selected_user_ids
                ],
                ignore_conflicts=True,
            )

        clear_project_create_session(self.request)
        request.session["success_message"] = {
            "heading": "Project created",
            "message": "You can now generate keys for the AI gateway API",
        }

        return redirect("projects:project_detail", slug=project.slug)


class ProjectUsersDetailView(DetailView):
    template_name = "projects/user-list.html"
    context_object_name = "project"
    model = Project

    def get_queryset(self):
        return (
            Project.objects.filter(user_permissions__user=self.request.user)
            .prefetch_related(
                Prefetch(
                    "user_permissions",
                    queryset=ProjectUserPermissions.objects.select_related("user"),
                )
            )
            .distinct()
        )

    def get_context_data(self, **kwargs):
        self.request.session.pop(ADD_USER_SESSION_KEY, None)
        context = super().get_context_data(**kwargs)
        context["success_message"] = self.request.session.pop("success_message", None)
        return context


class ProjectDeleteView(DeleteView):
    """
    Will need additional checks for user permissions to ensure
    the user has access to delete the project.
    """

    template_name = "projects/delete-confirm.html"
    context_object_name = "project"
    model = Project
    success_url = reverse_lazy("projects:projects_list")

    def get_queryset(self):
        return Project.objects.filter(
            user_permissions__user=self.request.user,
            user_permissions__role="admin",
        ).distinct()

    def form_valid(self, form):
        response = super().form_valid(form)
        self.request.session["success_message"] = {
            "heading": "Project deleted",
        }
        return response


class ProjectAddUsersView(ExistingProjectMixin, ProjectUserSelectionFormView):
    template_name = "projects/user-add.html"

    def get_success_url(self):
        return reverse(
            "projects:project_users_add_confirm",
            kwargs={"slug": self.get_project().slug},
        )


class ProjectAddUsersConfirmView(ExistingProjectMixin, ProjectUserSelectionSessionMixin, View):
    template_name = "projects/user-add-confirm.html"

    def get_selected_users(self):
        selected_user_ids = self.get_selected_user_ids()
        return User.objects.filter(id__in=selected_user_ids).order_by("email")

    def get(self, request, *args, **kwargs):
        project = self.get_project()
        selected_users = list(self.get_selected_users())
        if not selected_users:
            return redirect("projects:project_users_add", slug=project.slug)

        context = {"project": project, "selected_users": selected_users}
        return render(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        project = self.get_project()
        selected_user_ids = self.get_selected_user_ids()

        if not selected_user_ids:
            return redirect("projects:project_users_add", slug=project.slug)

        existing_user_ids = set(
            ProjectUserPermissions.objects.filter(
                project=project,
                user_id__in=selected_user_ids,
            ).values_list("user_id", flat=True)
        )
        create_for_user_ids = [
            user_id for user_id in selected_user_ids if user_id not in existing_user_ids
        ]

        with transaction.atomic():
            ProjectUserPermissions.objects.bulk_create(
                [
                    ProjectUserPermissions(
                        project=project,
                        user_id=user_id,
                        role="admin",
                    )
                    for user_id in create_for_user_ids
                ],
                ignore_conflicts=True,
            )

        self.clear_selected_user_ids()
        request.session["success_message"] = {
            "heading": "Project member added",
        }

        return redirect("projects:project_users", slug=project.slug)


class ProjectRemoveUserView(DeleteView):
    """
    Will need additional checks for user permissions to ensure
    the user can remove users from the project.
    """

    template_name = "projects/user-remove-confirm.html"
    context_object_name = "membership"
    model = ProjectUserPermissions

    def get_object(self, queryset=None):
        return get_object_or_404(
            ProjectUserPermissions.objects.select_related("project", "user")
            .filter(project__user_permissions__user=self.request.user)
            .distinct(),
            project__slug=self.kwargs["slug"],
            user_id=self.kwargs["user_id"],
        )

    def get_success_url(self):
        return reverse("projects:project_users", kwargs={"slug": self.kwargs["slug"]})

    def delete(self, request, *args, **kwargs):
        membership = self.get_object()
        user_name = membership.user.full_name
        response = super().delete(request, *args, **kwargs)
        self.request.session["success_message"] = {
            "heading": f"You have removed {user_name} from this project",
        }
        return response
