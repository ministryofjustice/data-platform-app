from django.views.generic.detail import DetailView
from django.views.generic.list import ListView

from projects.models import Project


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
