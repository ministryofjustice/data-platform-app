"""Standalone entrypoint for the MCP server."""

from __future__ import annotations

import asyncio
import os
import sys

import django
import dotenv


def main() -> None:
    """Start the MCP server from the command line."""
    dotenv.load_dotenv()
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "data_platform_app.settings.local")
    django.setup()

    from data_platform_mcp.server import DataPlatformMCPServer

    print("Starting MCP server over stdio...", file=sys.stderr, flush=True)
    server = DataPlatformMCPServer()
    asyncio.run(server.run())


if __name__ == "__main__":
    main()
