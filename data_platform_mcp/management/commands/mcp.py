"""Django management command to run the MCP server."""

import asyncio
import logging
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from data_platform_mcp.server import DataPlatformMCPServer

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Run the Data Platform MCP server."""

    help = "Start the MCP server for the Data Platform Application"

    def add_arguments(self, parser: Any) -> None:
        """Add command arguments."""
        parser.add_argument(
            "--transport",
            type=str,
            default="stdio",
            choices=["stdio", "sse"],
            help="MCP transport type (default: stdio)",
        )
        parser.add_argument(
            "--port",
            type=int,
            default=8765,
            help="Port for SSE transport (default: 8765)",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Run the MCP server."""
        transport = options["transport"]

        try:
            self.stdout.write(
                self.style.SUCCESS(f"Starting Data Platform MCP Server (transport: {transport})")
            )

            server = DataPlatformMCPServer()

            # Run the server
            asyncio.run(server.run(transport=transport))

        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("\nServer interrupted by user"))
        except Exception as e:
            logger.exception("Error running MCP server")
            raise CommandError(f"Failed to start MCP server: {str(e)}") from e
