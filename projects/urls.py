from django.urls import path

from projects.views import (
    EntraUserSearchView,
    ProjectAddUsersConfirmView,
    ProjectAddUsersView,
    ProjectCreateAddUsersView,
    ProjectCreateConfirmView,
    ProjectCreateView,
    ProjectDeleteView,
    ProjectDetailView,
    ProjectListView,
    ProjectRemoveUserView,
    ProjectUsersDetailView,
)

app_name = "projects"

urlpatterns = [
    path("", ProjectListView.as_view(), name="projects_list"),
    path("entra-users/search/", EntraUserSearchView.as_view(), name="entra_user_search"),
    path("create/", ProjectCreateView.as_view(), name="project_create"),
    path(
        "create/add-users/", ProjectCreateAddUsersView.as_view(), name="project_create_add_users"
    ),
    path("create/confirm/", ProjectCreateConfirmView.as_view(), name="project_create_confirm"),
    path("<uuid:uuid>/", ProjectDetailView.as_view(), name="project_detail"),
    path("<uuid:uuid>/users/", ProjectUsersDetailView.as_view(), name="project_users"),
    path("<uuid:uuid>/users/add/", ProjectAddUsersView.as_view(), name="project_users_add"),
    path(
        "<uuid:uuid>/users/add/confirm/",
        ProjectAddUsersConfirmView.as_view(),
        name="project_users_add_confirm",
    ),
    path("<uuid:uuid>/delete/", ProjectDeleteView.as_view(), name="project_delete"),
    path(
        "<uuid:uuid>/users/<int:user_id>/remove/",
        ProjectRemoveUserView.as_view(),
        name="project_user_remove",
    ),
]
