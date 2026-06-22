from django.urls import path

from projects.views import ListView

app_name = "projects"

urlpatterns = [
    path("", ListView.as_view(), name="projects_list"),
]
