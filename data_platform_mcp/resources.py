"""Resources for operational data access via MCP.

Provides read-only access to projects, teams, and keys with proper authorization.
"""

import json
import logging

from django.contrib.auth import get_user_model

from ai_gateway.models import Key, Team
from data_platform_mcp.auth import MCPAuthorization
from data_platform_mcp.models import MCPAuditor

logger = logging.getLogger(__name__)
User = get_user_model()


class OperationalDataReader:
    """Reads operational data with authorization and audit logging."""

    def __init__(self, user: User, ip_address: str | None = None):
        """Initialize reader with user context.

        Args:
            user: The authenticated user
            ip_address: IP address of the request origin
        """
        self.user = user
        self.auth = MCPAuthorization(user)
        self.auditor = MCPAuditor(user=user, ip_address=ip_address)

    def read_projects(self) -> str:
        """Read projects accessible to the user.

        Returns:
            JSON string containing list of accessible projects
        """
        try:
            projects = self.auth.get_accessible_projects()

            projects_data = [
                {
                    "id": str(project.uuid),
                    "name": project.name,
                    "description": project.description,
                    "created": project.created.isoformat(),
                    "modified": project.modified.isoformat(),
                }
                for project in projects
            ]

            # Log successful read
            for project in projects:
                self.auditor.log_project_read(
                    project_id=str(project.uuid),
                    success=True,
                )

            logger.info(
                "Operational data: projects read",
                extra={
                    "user_id": self.user.id,
                    "project_count": len(projects),
                },
            )

            return json.dumps({"projects": projects_data})

        except Exception as e:
            logger.error(
                "Error reading projects",
                extra={"user_id": self.user.id, "error": str(e)},
            )
            raise

    def read_teams(self) -> str:
        """Read AI Gateway teams for accessible projects.

        Returns:
            JSON string containing list of accessible teams
        """
        try:
            projects = self.auth.get_accessible_projects()
            teams = Team.objects.filter(project__in=projects).select_related("project")

            teams_data = [
                {
                    "id": str(team.id),
                    "project_id": str(team.project.uuid),
                    "litellm_team_id": team.litellm_team_id,
                    "created": team.created.isoformat(),
                    "modified": team.modified.isoformat(),
                }
                for team in teams
            ]

            # Log reads
            for team in teams:
                self.auditor.log_team_read(
                    team_id=str(team.id),
                    success=True,
                )

            logger.info(
                "Operational data: teams read",
                extra={
                    "user_id": self.user.id,
                    "team_count": len(teams),
                },
            )

            return json.dumps({"teams": teams_data})

        except Exception as e:
            logger.error(
                "Error reading teams",
                extra={"user_id": self.user.id, "error": str(e)},
            )
            raise

    def read_keys(self, project_id: str | None = None) -> str:
        """Read API keys for accessible projects.

        Args:
            project_id: Optional project UUID to filter by

        Returns:
            JSON string containing list of accessible keys
        """
        try:
            if project_id:
                # Authorize access to specific project
                project = self.auth.authorize_project_access(project_id)
                projects = [project]
            else:
                # Get all accessible projects
                projects = self.auth.get_accessible_projects()

            keys = Key.objects.filter(project__in=projects).select_related("project", "created_by")

            keys_data = [
                {
                    "id": str(key.id),
                    "project_id": str(key.project.uuid),
                    "name": key.name,
                    "masked_key": key.masked_key,
                    "models": key.models,
                    "created_by": key.created_by.email if key.created_by else None,
                    "created": key.created.isoformat(),
                    "modified": key.modified.isoformat(),
                }
                for key in keys
            ]

            # Log reads
            for key in keys:
                self.auditor.log_key_read(
                    key_id=str(key.id),
                    project_id=str(key.project.uuid),
                    success=True,
                )

            logger.info(
                "Operational data: keys read",
                extra={
                    "user_id": self.user.id,
                    "key_count": len(keys),
                    "project_filter": project_id,
                },
            )

            return json.dumps({"keys": keys_data})

        except Exception as e:
            logger.error(
                "Error reading keys",
                extra={
                    "user_id": self.user.id,
                    "project_id": project_id,
                    "error": str(e),
                },
            )
            raise
