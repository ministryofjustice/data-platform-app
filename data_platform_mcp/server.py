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
from typing import Any

import django
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    AnyUrl,
    Resource,
    TextContent,
    Tool,
)

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
            "Example: export MCP_USER_EMAIL=you@example.com"
        )

    try:
        return User.objects.get(email=email)
    except User.DoesNotExist:
        raise RuntimeError(
            f"No user found with email '{email}'. "
            "Ensure the user exists in the database and MCP_USER_EMAIL is correct."
        )


class DataPlatformMCPServer:
    """MCP server for Data Platform Application.

    Exposes:
    - Resources: Operational data (projects, users, teams, keys)
    - Tools: API key lifecycle management (create, list, delete, rotate)
    """

    def __init__(self):
        """Initialise the MCP server."""
        self.server = Server("data-platform")
        self._register_resources()
        self._register_tools()

    def _register_resources(self) -> None:
        """Register data resources."""

        @self.server.list_resources()
        async def list_resources() -> list[Resource]:
            """List available resources."""
            return [
                Resource(
                    uri=AnyUrl("mcp://data-platform/projects"),
                    name="Projects",
                    description="List of projects accessible to the authenticated user",
                    mimeType="application/json",
                ),
                Resource(
                    uri=AnyUrl("mcp://data-platform/teams"),
                    name="AI Gateway Teams",
                    description="AI Gateway teams for user's projects",
                    mimeType="application/json",
                ),
                Resource(
                    uri=AnyUrl("mcp://data-platform/keys"),
                    name="API Keys",
                    description="API keys for user's projects (secrets masked)",
                    mimeType="application/json",
                ),
            ]

        @self.server.read_resource()
        async def read_resource(uri: AnyUrl) -> str:
            """Read a resource by URI."""
            uri_str = str(uri)
            user = _get_current_user()

            from data_platform_mcp.resources import OperationalDataReader

            reader = OperationalDataReader(user=user)

            if uri_str == "mcp://data-platform/projects":
                return reader.read_projects()
            elif uri_str == "mcp://data-platform/teams":
                return reader.read_teams()
            elif uri_str == "mcp://data-platform/keys":
                return reader.read_keys()
            else:
                raise ValueError(f"Unknown resource URI: {uri_str}")

    def _register_tools(self) -> None:
        """Register available tools."""

        @self.server.list_tools()
        async def list_tools() -> list[Tool]:
            """List available tools."""
            return [
                Tool(
                    name="create_api_key",
                    description="Create a new API key for a project. Requires admin role on the project.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "project_id": {
                                "type": "string",
                                "description": "UUID of the project",
                            },
                            "name": {
                                "type": "string",
                                "description": "Name for the API key (1-255 characters, unique within project)",
                            },
                            "models": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of model IDs to grant access to (1-50 models)",
                            },
                        },
                        "required": ["project_id", "name", "models"],
                    },
                ),
                Tool(
                    name="delete_api_key",
                    description="Delete an API key. Requires admin role on the project.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "key_id": {
                                "type": "string",
                                "description": "ID of the key to delete",
                            },
                            "project_id": {
                                "type": "string",
                                "description": "UUID of the project the key belongs to",
                            },
                        },
                        "required": ["key_id", "project_id"],
                    },
                ),
                Tool(
                    name="list_api_keys",
                    description="List API keys for a project. Available to all project members.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "project_id": {
                                "type": "string",
                                "description": "UUID of the project",
                            },
                        },
                        "required": ["project_id"],
                    },
                ),
                Tool(
                    name="rotate_api_key",
                    description="Rotate an API key (generates a new secret). Requires admin role on the project.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "key_id": {
                                "type": "string",
                                "description": "ID of the key to rotate",
                            },
                            "project_id": {
                                "type": "string",
                                "description": "UUID of the project the key belongs to",
                            },
                        },
                        "required": ["key_id", "project_id"],
                    },
                ),
            ]

        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
            """Handle tool calls."""
            user = _get_current_user()

            from data_platform_mcp.auth import MCPAuthorizationError
            from data_platform_mcp.resources import OperationalDataReader
            from data_platform_mcp.tools import APIKeyManager, APIKeyOperationError

            try:
                if name == "list_api_keys":
                    reader = OperationalDataReader(user=user)
                    result = reader.read_keys(project_id=arguments["project_id"])
                    return [TextContent(type="text", text=result)]

                manager = APIKeyManager(user=user)

                if name == "create_api_key":
                    key = manager.create_key(
                        project_id=arguments["project_id"],
                        name=arguments["name"],
                        models=arguments["models"],
                    )
                    return [TextContent(type="text", text=json.dumps(key, indent=2))]

                elif name == "delete_api_key":
                    manager.delete_key(
                        key_id=arguments["key_id"],
                        project_id=arguments["project_id"],
                    )
                    return [TextContent(type="text", text=json.dumps({"deleted": True, "key_id": arguments["key_id"]}))]

                elif name == "rotate_api_key":
                    key = manager.rotate_key(
                        key_id=arguments["key_id"],
                        project_id=arguments["project_id"],
                    )
                    return [TextContent(type="text", text=json.dumps(key, indent=2))]

                else:
                    raise ValueError(f"Unknown tool: {name}")

            except MCPAuthorizationError as e:
                return [TextContent(type="text", text=json.dumps({"error": "authorization_denied", "message": str(e)}))]
            except APIKeyOperationError as e:
                return [TextContent(type="text", text=json.dumps({"error": "operation_failed", "message": str(e)}))]
            except Exception as e:
                logger.exception("Unexpected error in tool %s", name)
                return [TextContent(type="text", text=json.dumps({"error": "internal_error", "message": str(e)}))]

    async def run(self, transport: str = "stdio") -> None:
        """Run the MCP server with the specified transport.

        Args:
            transport: Transport type — 'stdio' (default) for CLI/Claude Desktop use.
        """
        if transport == "stdio":
            async with stdio_server() as (read_stream, write_stream):
                await self.server.run(
                    read_stream,
                    write_stream,
                    self.server.create_initialization_options(),
                )
        else:
            raise NotImplementedError(f"Transport '{transport}' is not yet supported. Use 'stdio'.")
