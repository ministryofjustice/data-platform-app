from django.contrib.auth.backends import BaseBackend

from projects.models import Project, ProjectMembershipPermission


class ProjectPermissionBackend(BaseBackend):
    """
    Checks if a user has the given permission for a project
    """

    def has_perm(self, user_obj, perm, obj=None) -> bool:
        if not user_obj.is_authenticated:
            return False

        if not isinstance(obj, Project):
            return False

        app_label, _, codename = perm.partition(".")

        if app_label != "projects" or not codename:
            return False

        return ProjectMembershipPermission.objects.filter(
            membership__user=user_obj,
            membership__project=obj,
            permission__content_type__app_label=app_label,
            permission__content_type__model="project",
            permission__codename=codename,
        ).exists()
