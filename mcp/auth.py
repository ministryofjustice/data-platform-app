"""Authorization checks for MCP operations.

Enforces explicit authorization with audit logging.
"""

import logging

from django.contrib.auth import get_user_model

from projects.models import Project, ProjectUserPermissions

logger = logging.getLogger(__name__)
User = get_user_model()


class MCPAuthorizationError(Exception):
    """Raised when MCP operation is not authorized."""

    pass


class MCPAuthorization:
    """Authorization checks for MCP operations."""

    ALLOWED_ROLES = {"admin", "member"}
    ADMIN_ONLY_ROLES = {"admin"}

    def __init__(self, user: User):
        """Initialize authorization context.

        Args:
            user: The authenticated user performing the operation
        """
        self.user = user

    def authorize_project_access(
        self,
        project_id: str,
        required_role: str | None = None,
    ) -> Project:
        """Check if user can access a project.

        Args:
            project_id: UUID of the project to access
            required_role: Specific role required (e.g. 'admin'). If None, any access allowed.

        Returns:
            The authorized Project object

        Raises:
            MCPAuthorizationError: If access is denied
        """
        try:
            project = Project.objects.get(uuid=project_id)
        except Project.DoesNotExist:
            logger.warning(
                "Unauthorized access attempt to non-existent project",
                extra={"user_id": self.user.id, "project_id": project_id},
            )
            raise MCPAuthorizationError(f"Project {project_id} not found or access denied")

        # Superusers have automatic access to all projects
        if self.user.is_superuser:
            logger.debug(
                "Superuser project access granted",
                extra={
                    "user_id": self.user.id,
                    "project_id": project_id,
                },
            )
            return project

        # Check if user has access to this project
        try:
            permission = ProjectUserPermissions.objects.get(
                project=project,
                user=self.user,
            )
        except ProjectUserPermissions.DoesNotExist:
            logger.warning(
                "Unauthorized project access attempt",
                extra={
                    "user_id": self.user.id,
                    "project_id": project_id,
                    "action": "project_access",
                },
            )
            raise MCPAuthorizationError(f"User does not have access to project {project_id}")

        # Check role if specified
        if required_role and permission.role not in self.ALLOWED_ROLES:
            logger.warning(
                "Insufficient role for MCP operation",
                extra={
                    "user_id": self.user.id,
                    "project_id": project_id,
                    "required_role": required_role,
                    "user_role": permission.role,
                },
            )
            raise MCPAuthorizationError(f"Insufficient permissions for project {project_id}")

        if required_role and permission.role != required_role:
            logger.warning(
                "MCP operation requires higher privileges",
                extra={
                    "user_id": self.user.id,
                    "project_id": project_id,
                    "required_role": required_role,
                    "user_role": permission.role,
                },
            )
            raise MCPAuthorizationError(
                f"User role {permission.role} insufficient for {required_role} operation"
            )

        logger.debug(
            "Project access authorized",
            extra={
                "user_id": self.user.id,
                "project_id": project_id,
                "user_role": permission.role,
            },
        )
        return project

    def authorize_admin_access(self) -> None:
        """Check if user is a superuser.

        Raises:
            MCPAuthorizationError: If user is not a superuser
        """
        if not self.user.is_superuser:
            logger.warning(
                "Unauthorized admin access attempt",
                extra={"user_id": self.user.id},
            )
            raise MCPAuthorizationError("Admin access required")

    def authorize_key_creation(self, project_id: str) -> Project:
        """Check if user can create API keys for a project.

        Args:
            project_id: UUID of the project

        Returns:
            The authorized Project object

        Raises:
            MCPAuthorizationError: If operation is not allowed
        """
        # Only project admins can create keys
        return self.authorize_project_access(project_id, required_role="admin")

    def authorize_key_deletion(self, project_id: str) -> Project:
        """Check if user can delete API keys for a project.

        Args:
            project_id: UUID of the project

        Returns:
            The authorized Project object

        Raises:
            MCPAuthorizationError: If operation is not allowed
        """
        # Only project admins can delete keys
        return self.authorize_project_access(project_id, required_role="admin")

    def authorize_key_rotation(self, project_id: str) -> Project:
        """Check if user can rotate API keys for a project.

        Args:
            project_id: UUID of the project

        Returns:
            The authorized Project object

        Raises:
            MCPAuthorizationError: If operation is not allowed
        """
        # Only project admins can rotate keys
        return self.authorize_project_access(project_id, required_role="admin")

    def get_accessible_projects(self) -> list[Project]:
        """Get all projects accessible to the user.

        Returns:
            List of Project objects the user has access to
        """
        if self.user.is_superuser:
            return list(Project.objects.all())

        return list(
            Project.objects.filter(
                user_permissions__user=self.user,
            ).distinct()
        )
