from django.urls import path

from projects.views import AddMembersView, CheckDetailsView, CreateProjectView, ListView

app_name = "projects"

urlpatterns = [
    path("", ListView.as_view(), name="projects_list"),
    path("create/", CreateProjectView.as_view(), name="create_project"),
    path("create/add-members/", AddMembersView.as_view(), name="add_members"),
    path("create/check-details/", CheckDetailsView.as_view(), name="check_details"),
]
