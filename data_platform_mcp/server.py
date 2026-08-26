"""MCP server for the Data Platform Application.

Provides access to operational data and API key lifecycle management
with user-scoped access control and full audit trail.

User identity is resolved from the MCP_USER_EMAIL environment variable,
which must be set to the email of an existing Django user before starting
the server. This is the standard approach for stdio-transport MCP servers
where there is no HTTP request context.
"""

import json
import logging
import os
from typing import Annotated

from asgiref.sync import sync_to_async
from mcp.server import MCPServer
from pydantic import Field

logger = logging.getLogger(__name__)


def _get_current_user():
    """Resolve the authenticated user from MCP_USER_EMAIL environment variable.

    Returns:
        User instance

    Raises:
        RuntimeError: If MCP_USER_EMAIL is not set or user not found
    """
    from django.contrib.auth import get_user_model

    User = get_user_model()

    email = os.environ.get("MCP_USER_EMAIL")
    if not email:
        raise RuntimeError(
            "MCP_USER_EMAIL environment variable must be set to the email of a Django user. "
            "Example: export MCP_USER_EMAIL=admin@example.com"
        )

    try:
        return User.objects.get(email=email)
    except User.DoesNotExist:
        raise RuntimeError(
            f"No user found with email '{email}'. "
            "Ensure the user exists in the database and MCP_USER_EMAIL is correct."
        ) from None


async def _run_tool(name, operation):
    """Run a tool operation, converting known domain errors into JSON payloads."""
    from data_platform_mcp.auth import MCPAuthorizationError
    from data_platform_mcp.tools import APIKeyOperationError

    try:
        return await operation()
    except MCPAuthorizationError as e:
        return json.dumps({"error": "authorization_denied", "message": str(e)})
    except APIKeyOperationError as e:
        return json.dumps({"error": "operation_failed", "message": str(e)})
    except Exception as e:
        logger.exception("Unexpected error in tool %s", name)
        return json.dumps({"error": "internal_error", "message": str(e)})


class DataPlatformMCPServer:
    """MCP server for Data Platform Application.

    Exposes:
    - Resources: Operational data (projects, users, teams, keys)
    - Tools: API key lifecycle management (create, list, delete, rotate)
    """

    def __init__(self):
        """Initialise the MCP server."""
        self.server = MCPServer("data-platform")
        self._register_resources()
        self._register_tools()

    async def _current_user(self):
        """Resolve the authenticated user off the event loop."""
        return await sync_to_async(_get_current_user, thread_sensitive=False)()

    def _register_resources(self) -> None:
        """Register data resources."""

        @self.server.resource(
            "mcp://data-platform/projects",
            name="Projects",
            description="List of projects accessible to the authenticated user",
            mime_type="application/json",
        )
        async def read_projects() -> str:
            from data_platform_mcp.resources import OperationalDataReader

            reader = OperationalDataReader(user=await self._current_user())
            return await sync_to_async(reader.read_projects, thread_sensitive=False)()

        @self.server.resource(
            "mcp://data-platform/teams",
            name="AI Gateway Teams",
            description="AI Gateway teams for user's projects",
            mime_type="application/json",
        )
        async def read_teams() -> str:
            from data_platform_mcp.resources import OperationalDataReader

            reader = OperationalDataReader(user=await self._current_user())
            return await sync_to_async(reader.read_teams, thread_sensitive=False)()

        @self.server.resource(
            "mcp://data-platform/keys",
            name="API Keys",
            description="API keys for user's projects (secrets masked)",
            mime_type="application/json",
        )
        async def read_keys() -> str:
            from data_platform_mcp.resources import OperationalDataReader

            reader = OperationalDataReader(user=await self._current_user())
            return await sync_to_async(reader.read_keys, thread_sensitive=False)()

    def _register_tools(self) -> None:
        """Register available tools."""

        @self.server.tool(
            name="list_projects",
            description="List all projects accessible to the authenticated user.",
        )
        async def list_projects() -> str:
            async def _op() -> str:
                from data_platform_mcp.resources import OperationalDataReader

                reader = OperationalDataReader(user=await self._current_user())
                return await sync_to_async(reader.read_projects, thread_sensitive=False)()

            return await _run_tool("list_projects", _op)

        @self.server.tool(
            name="list_api_keys",
            description="List API keys for a project. Available to all project members.",
        )
        async def list_api_keys(
            project_id: Annotated[str, Field(description="UUID of the project")],
        ) -> str:
            async def _op() -> str:
                from data_platform_mcp.resources import OperationalDataReader

                reader = OperationalDataReader(user=await self._current_user())
                return await sync_to_async(reader.read_keys, thread_sensitive=False)(
                    project_id=project_id
                )

            return await _run_tool("list_api_keys", _op)

        @self.server.tool(
            name="create_api_key",
            description="Create a new API key for a project. Requires admin role on the project.",
        )
        async def create_api_key(
            project_id: Annotated[str, Field(description="UUID of the project")],
            name: Annotated[
                str,
                Field(
                    description="Name for the API key (1-255 characters, unique within project)"
                ),
            ],
            models: Annotated[
                list[str],
                Field(description="List of model IDs to grant access to (1-50 models)"),
            ],
        ) -> str:
            async def _op() -> str:
                from data_platform_mcp.tools import APIKeyManager

                manager = APIKeyManager(user=await self._current_user())
                key = await sync_to_async(manager.create_key, thread_sensitive=False)(
                    project_id=project_id,
                    name=name,
                    models=models,
                )
                return json.dumps(key, indent=2)

            return await _run_tool("create_api_key", _op)

        @self.server.tool(
            name="delete_api_key",
            description="Delete an API key. Requires admin role on the project.",
        )
        async def delete_api_key(
            key_id: Annotated[str, Field(description="ID of the key to delete")],
            project_id: Annotated[
                str, Field(description="UUID of the project the key belongs to")
            ],
        ) -> str:
            async def _op() -> str:
                from data_platform_mcp.tools import APIKeyManager

                manager = APIKeyManager(user=await self._current_user())
                await sync_to_async(manager.delete_key, thread_sensitive=False)(
                    key_id=key_id,
                    project_id=project_id,
                )
                return json.dumps({"deleted": True, "key_id": key_id})

            return await _run_tool("delete_api_key", _op)

        @self.server.tool(
            name="rotate_api_key",
            description=(
                "Rotate an API key (generates a new secret). Requires admin role on the project."
            ),
        )
        async def rotate_api_key(
            key_id: Annotated[str, Field(description="ID of the key to rotate")],
            project_id: Annotated[
                str, Field(description="UUID of the project the key belongs to")
            ],
        ) -> str:
            async def _op() -> str:
                from data_platform_mcp.tools import APIKeyManager

                manager = APIKeyManager(user=await self._current_user())
                key = await sync_to_async(manager.rotate_key, thread_sensitive=False)(
                    key_id=key_id,
                    project_id=project_id,
                )
                return json.dumps(key, indent=2)

            return await _run_tool("rotate_api_key", _op)

    async def run(self) -> None:
        """Run the MCP server over stdio."""
        await self.server.run_stdio_async()
