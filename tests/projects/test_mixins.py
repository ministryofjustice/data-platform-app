import pytest
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse

from projects.mixins import ProjectPermissionRequiredMixin
from projects.models import ProjectPermission


class StubView:
    def dispatch(self, request, *args, **kwargs):
        return HttpResponse("view called")


class ProjectScopedStubView(ProjectPermissionRequiredMixin, StubView):
    def __init__(self, project, permission_required):
        self._project = project
        self.permission_required = permission_required

    def get_project(self):
        return self._project


class TestProjectPermissionRequiredMixin:
    @pytest.mark.parametrize("perm", list(ProjectPermission))
    def test_has_permission_true_when_user_has_permission(
        self, rf, project, user, grant_project_permission, perm
    ):
        grant_project_permission(project, user, perm)
        view = ProjectScopedStubView(project, f"projects.{perm.value}")
        view.request = rf.get("/")
        view.request.user = user

        assert view.has_permission() is True

    @pytest.mark.parametrize("perm", list(ProjectPermission))
    def test_has_permission_false_when_user_lacks_permission(self, rf, project, user, perm):
        view = ProjectScopedStubView(project, f"projects.{perm.value}")
        view.request = rf.get("/")
        view.request.user = user

        assert view.has_permission() is False

    @pytest.mark.parametrize("perm", list(ProjectPermission))
    def test_has_permission_true_for_superuser_without_membership(
        self, rf, project, superuser, perm
    ):
        view = ProjectScopedStubView(project, f"projects.{perm.value}")
        view.request = rf.get("/")
        view.request.user = superuser

        assert view.has_permission() is True

    @pytest.mark.parametrize("perm", list(ProjectPermission))
    def test_dispatch_calls_view_when_user_has_permission(
        self, rf, project, user, grant_project_permission, perm
    ):
        grant_project_permission(project, user, perm)
        view = ProjectScopedStubView(project, f"projects.{perm.value}")
        view.request = rf.get("/")
        view.request.user = user

        response = view.dispatch(view.request)

        assert response.status_code == 200
        assert response.content == b"view called"

    @pytest.mark.parametrize("perm", list(ProjectPermission))
    def test_dispatch_raises_permission_denied_when_user_lacks_permission(
        self, rf, project, user, perm
    ):
        view = ProjectScopedStubView(project, f"projects.{perm.value}")
        view.request = rf.get("/")
        view.request.user = user

        with pytest.raises(PermissionDenied):
            view.dispatch(view.request)
