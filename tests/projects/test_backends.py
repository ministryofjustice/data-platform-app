import pytest

from projects.backends import ProjectPermissionBackend
from projects.models import ProjectPermission


class TestUserHasPerm:
    @pytest.mark.parametrize("perm", list(ProjectPermission))
    def test_user_has_permission(self, project, user, perm, grant_project_permission):
        backend = ProjectPermissionBackend()
        grant_project_permission(project, user, perm)
        user_has_perm = backend.has_perm(user, f"projects.{perm}", project)
        assert user_has_perm is True

    @pytest.mark.parametrize(
        "perm",
        list(ProjectPermission),
    )
    def test_user_does_not_have_permission(self, project, user, perm):
        backend = ProjectPermissionBackend()
        user_has_perm = backend.has_perm(user, f"projects.{perm}", project)
        assert user_has_perm is False
