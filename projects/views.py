from django.db import transaction
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.urls.base import reverse_lazy
from django.views.generic.base import View
from django.views.generic.detail import DetailView
from django.views.generic.edit import DeleteView, FormView
from django.views.generic.list import ListView

from projects.forms import build_project_add_member_formset
from projects.models import Project, ProjectUserPermissions
from users.models import User

ADD_USER_SESSION_KEY = "project_user_add_selection"


# Create your views here.
class ProjectListView(ListView):
    template_name = "projects/list.html"
    context_object_name = "user_projects"
    model = Project

    def get_queryset(self):
        """
        set PK to whatever user you've created in db.
        Code will be deleted once user auth is implemented
        """
        # pk = 4
        # user = User.objects.get(pk=pk)
        # return user.projects.all()
        # Once entra in - this line will be used to get the projects for the logged in user
        return self.request.user.projects.all()


class ProjectDetailView(DetailView):
    template_name = "projects/detail.html"
    context_object_name = "project"
    model = Project

    def get_queryset(self):
        # TODO: filter by user permissions to ensure the user has access to the project
        return Project.objects.select_related("business_unit", "created_by").prefetch_related(
            "users", "user_permissions__user"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["success_message"] = self.request.session.pop("success_message", None)
        return context


class ProjectUsersDetailView(DetailView):
    template_name = "projects/user-list.html"
    context_object_name = "project"
    model = Project

    def get_queryset(self):
        # TODO: filter by user permissions to ensure the user has access to the project
        return Project.objects.prefetch_related(
            Prefetch(
                "user_permissions",
                queryset=ProjectUserPermissions.objects.select_related("user"),
            )
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


class ProjectAddUsersBaseView(View):
    def get_project(self):
        if not hasattr(self, "_project"):
            self._project = get_object_or_404(Project, slug=self.kwargs["slug"])
        return self._project

    def get_selected_user_ids(self):
        project_id_map = self.request.session.get(ADD_USER_SESSION_KEY, {})
        selected_user_ids = project_id_map.get(str(self.get_project().id), [])
        return [int(user_id) for user_id in selected_user_ids]

    def set_selected_user_ids(self, user_ids):
        project_id_map = self.request.session.get(ADD_USER_SESSION_KEY, {})
        project_id_map[str(self.get_project().id)] = user_ids
        self.request.session[ADD_USER_SESSION_KEY] = project_id_map

    def clear_selected_user_ids(self):
        self.request.session.pop(ADD_USER_SESSION_KEY, None)


class ProjectAddUsersView(ProjectAddUsersBaseView, FormView):
    template_name = "projects/user-add.html"

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
        context["project"] = self.get_project()
        context["formset"] = context["form"]
        return context

    def get_success_url(self):
        return reverse(
            "projects:project_users_add_confirm",
            kwargs={"slug": self.get_project().slug},
        )

    def form_valid(self, form):
        self.set_selected_user_ids(form.selected_user_ids)
        return redirect(self.get_success_url())


class ProjectAddUsersConfirmView(ProjectAddUsersBaseView):
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
        # Ensures the membership belongs to the project in the URL.
        return get_object_or_404(
            ProjectUserPermissions.objects.select_related("project", "user"),
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
