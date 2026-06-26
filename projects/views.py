from django.db.models import Prefetch
from django.urls.base import reverse_lazy
from django.views.generic.detail import DetailView
from django.views.generic.edit import DeleteView
from django.views.generic.list import ListView

from projects.models import Project, ProjectUserPermissions


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
