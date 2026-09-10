import pytest

from projects.backends import ProjectPermissionBackend
from projects.models import ProjectMembership, ProjectMembershipPermission, ProjectPermission


class TestUserHasPerm:
    def add_perm(self, project, user, perm):
        # Get the membership object for the user in the project
        membership = ProjectMembership.objects.get(project=project, user=user)

        ProjectMembershipPermission.objects.get_or_create(
            membership=membership,
            permission=perm,
            defaults={
                "granted_by": user,
            },
        )

    @pytest.mark.parametrize(
        "perm",
        [
            (ProjectPermission.MANAGE_API_KEYS),
            (ProjectPermission.MANAGE_MEMBERS),
        ],
    )
    def test_user_has_permission(self, project, user, perm):
        backend = ProjectPermissionBackend()
        self.add_perm(project, user, perm)
        user_has_perm = backend.has_perm(user, f"projects.{perm}", project)
        assert user_has_perm is True

    @pytest.mark.parametrize(
        "perm",
        [
            (ProjectPermission.MANAGE_API_KEYS),
            (ProjectPermission.MANAGE_MEMBERS),
        ],
    )
    def test_user_does_not_have_permission(self, project, user, perm):
        backend = ProjectPermissionBackend()
        user_has_perm = backend.has_perm(user, f"projects.{perm}", project)
        assert user_has_perm is False
