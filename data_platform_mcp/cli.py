"""Standalone entrypoint for the MCP server."""

from __future__ import annotations

import os

import django


def main() -> None:
    """Start the MCP server from the command line."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "data_platform_app.settings.local")
    django.setup()

    from data_platform_mcp.server import DataPlatformMCPServer

    server = DataPlatformMCPServer()
    server.run()


if __name__ == "__main__":
    main()
