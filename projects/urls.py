from django.urls import path

from projects.views import (
    ProjectAddUsersConfirmView,
    ProjectAddUsersView,
    ProjectDeleteView,
    ProjectDetailView,
    ProjectListView,
    ProjectRemoveUserView,
    ProjectUsersDetailView,
)

app_name = "projects"

urlpatterns = [
    path("", ProjectListView.as_view(), name="projects_list"),
    path("<slug:slug>/", ProjectDetailView.as_view(), name="project_detail"),
    path("<slug:slug>/users/", ProjectUsersDetailView.as_view(), name="project_users"),
    path("<slug:slug>/users/add/", ProjectAddUsersView.as_view(), name="project_users_add"),
    path(
        "<slug:slug>/users/add/confirm/",
        ProjectAddUsersConfirmView.as_view(),
        name="project_users_add_confirm",
    ),
    path("<slug:slug>/delete/", ProjectDeleteView.as_view(), name="project_delete"),
    path(
        "<slug:slug>/users/<int:user_id>/remove/",
        ProjectRemoveUserView.as_view(),
        name="project_user_remove",
    ),
]
