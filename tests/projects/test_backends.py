import pytest
from django.contrib.auth.models import Permission

from projects.backends import ProjectPermissionBackend
from projects.models import ProjectMembership, ProjectMembershipPermission, ProjectPermission


class TestUserHasPerm:
    def add_perm(self, project, user, perm):
        """Helper for creating project members with specific permissions"""
        membership = ProjectMembership.objects.get(project=project, user=user)
        permission = Permission.objects.get(
            codename=perm.value, content_type__app_label="projects", content_type__model="project"
        )
        ProjectMembershipPermission.objects.get_or_create(
            membership=membership,
            permission=permission,
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
