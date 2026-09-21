import pytest

from projects.models import ProjectPermission
from projects.templatetags.project_permissions import has_project_permission


class TestHasProjectPermission:
    @pytest.mark.parametrize("perm", list(ProjectPermission))
    def test_true_when_user_has_permission(self, project, user, grant_project_permission, perm):
        grant_project_permission(project, user, perm)

        assert has_project_permission(user, perm.permission_name, project) is True

    @pytest.mark.parametrize("perm", list(ProjectPermission))
    def test_false_when_user_lacks_permission(self, project, user, perm):
        assert has_project_permission(user, perm.permission_name, project) is False

    @pytest.mark.parametrize("perm", list(ProjectPermission))
    def test_true_for_superuser_without_membership(self, project, superuser, perm):
        assert has_project_permission(superuser, perm.permission_name, project) is True
