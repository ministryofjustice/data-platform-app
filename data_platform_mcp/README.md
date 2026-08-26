# MCP Server for Data Platform Application

This module provides a Model Context Protocol (MCP) server for secure access to operational data and API key lifecycle management in the Data Platform Application.

## Overview

The MCP server exposes two main capabilities:

### 1. Operational data resources (read-only)

- **Projects**: list accessible projects with metadata
- **Teams**: AI Gateway teams associated with projects
- **Keys**: API keys with usage information (sensitive data masked)

Access is controlled via Django project membership:

- **Superusers** see all data
- **Project members** see only their projects and related resources
- **Non-members** get access denied

### 2. API key lifecycle management (tools)

- `create_api_key`: create new API keys with model access specifications
- `delete_api_key`: revoke and remove API keys
- `rotate_api_key`: generate new credentials and invalidate the old secret
- `list_api_keys`: view keys for a project

Lifecycle operations are restricted to project administrators:

- Members cannot perform lifecycle operations
- All operations are audit-logged
- Creation is rate-limited by policy

## Security model

### Authentication

- Uses Django's built-in user model
- Expects MS Entra ID in production deployments
- Tests use `ModelBackend` for determinism

### Authorisation

- Explicit permission checks on every operation
- Role-based access control (`admin` / `member` per project)
- Superuser bypass for admin operations only

### Audit trail

Every operation is logged with:

- user performing the action
- resource affected
- action type
- success/failure status
- sanitised details with no secrets or tokens
- IP address where available

### Data protection

- Sensitive fields are encrypted at rest
- Secrets are never exposed via MCP resources
- Masked display shows only the last 4 characters
- Secrets are excluded from audit logs

## Installation & usage

```bash
uv sync
MCP_USER_EMAIL=admin@example.com make mcp
```

The `make mcp` target starts the server over stdio for use with MCP clients such as VS Code Copilot Chat.

## Configuration

Required environment variable:

- `MCP_USER_EMAIL`: email address of an existing Django user

Optional policy configuration is implemented in code for now; see the source in `data_platform_mcp/tools.py`.

## API reference

### Resources

- `mcp://data-platform/projects`
- `mcp://data-platform/teams`
- `mcp://data-platform/keys`

### Tools

- `create_api_key`
- `delete_api_key`
- `rotate_api_key`
- `list_api_keys`

## Future work

- Integrate the tools with the real AI Gateway API instead of the current in-process placeholder logic
- Add rate limiting and abuse protection if usage grows
- Add key expiration and lifecycle policies if compliance requires them
- Consider exposing metrics for tool usage and denial reasons

## Testing

The MCP implementation has targeted tests covering:

- authorisation and role enforcement
- resource access and masking
- key lifecycle operations and policy checks
- server wiring and identity resolution
