# MCP Server for Data Platform Application

This module provides a Model Context Protocol (MCP) server for secure access to operational data and API key lifecycle management in the Data Platform Application.

## Overview

The MCP server exposes two main capabilities:

### 1. Operational Data Resources (Read-Only)

- **Projects**: List of accessible projects with metadata
- **Teams**: AI Gateway teams associated with projects
- **Keys**: API keys with usage information (sensitive data masked)

Access is controlled via Django's project membership model:

- **Superusers** see all data
- **Project members** see only their projects and related resources
- **Non-members** get access denied

### 2. API Key Lifecycle Management (Tools)

- **create_api_key**: Create new API keys with model access specifications
- **delete_api_key**: Revoke and remove API keys
- **rotate_api_key**: Generate new credentials (old secret invalidated)
- **list_api_keys**: View keys for a project

Access is restricted to **project administrators only**:

- Members cannot perform lifecycle operations
- All operations are audit-logged
- Creation is rate-limited (max 10 keys per project)

## Security Model

### Authentication

- Uses Django's built-in user model
- Expects MS Entra ID for production deployments
- Tests use ModelBackend for determinism

### Authorization

- Explicit permission checks on every operation
- Role-based access control (admin/member per project)
- Superuser bypass for admin operations only

### Audit Trail

Every operation is logged in `MCPAuditLog`:

- User performing the action
- Resource affected (project/team/key)
- Action type (read/create/delete/rotate)
- Success/failure status
- Sanitized details (no secrets/tokens)
- IP address of origin

### Data Protection

- Sensitive fields (secrets, tokens) are encrypted at rest
- Never exposed via MCP resources
- Masked display shows only last 4 characters
- Secrets excluded from audit logs

## Installation & Configuration

### Prerequisites

- Django 6.1+
- MCP SDK 1.0+
- PostgreSQL (production) or SQLite (development)

### Setup

```bash
# Install dependencies (included in project)
uv sync

# Run migrations
uv run python manage.py migrate

# Start the MCP server
uv run python manage.py mcp --transport=stdio
```

### Configuration

Environment variables (optional):

- `MCP_MAX_KEYS_PER_PROJECT`: Maximum keys per project (default: 10)
- `MCP_RATE_LIMIT`: Requests per minute (default: unlimited)

## Usage

### With Claude Desktop

Add to `~/.config/Claude/claude_desktop_config.json` (Linux/macOS):

```json
{
  "mcpServers": {
    "data-platform": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/data-platform-app",
        "run",
        "python",
        "manage.py",
        "data_platform_mcp"
      ]
    }
  }
}
```

### With Custom Client

```python
import json
from data_platform_mcp.client import Client

client = Client("data-platform")
await client.connect("stdio")

# Read resources
projects = await client.read_resource("mcp://data-platform/projects")
keys = await client.read_resource("mcp://data-platform/keys?project_id=uuid")

# Call tools
result = await client.call_tool(
    "create_api_key",
    {"project_id": "project-uuid", "name": "Production Key", "models": ["gpt-4", "claude-3"]},
)
```

## Authorization Examples

### Scenario 1: Project Admin Creates Key

```
User: john@example.com (admin role in project "analytics")
Action: create_api_key for "analytics" project
Result: ✅ Success
Audit: Key creation logged with user, project, model list
```

### Scenario 2: Project Member Tries to Delete Key

```
User: jane@example.com (member role in project "reporting")
Action: delete_api_key in "reporting" project
Result: ❌ MCPAuthorizationError: "Insufficient permissions"
Audit: Failed delete attempt logged with denial reason
```

### Scenario 3: Superuser Reads All Projects

```
User: admin@example.com (is_superuser=True)
Action: read_projects resource
Result: ✅ Returns all projects + teams + keys
Audit: Access logged for compliance
```

## API Reference

### Resources

#### Projects

```
GET /mcp://data-platform/projects
Returns: {
  "projects": [
    {
      "id": "uuid",
      "name": "Project Name",
      "description": "...",
      "created": "2024-08-26T...",
      "modified": "2024-08-26T..."
    }
  ]
}
```

#### Teams

```
GET /mcp://data-platform/teams
Returns: {
  "teams": [
    {
      "id": "id",
      "project_id": "uuid",
      "litellm_team_id": "...",
      "created": "2024-08-26T...",
      "modified": "2024-08-26T..."
    }
  ]
}
```

#### Keys

```
GET /mcp://data-platform/keys?project_id=uuid
Returns: {
  "keys": [
    {
      "id": "id",
      "project_id": "uuid",
      "name": "My Key",
      "masked_key": "****abcd",
      "models": ["gpt-4"],
      "created_by": "user@example.com",
      "created": "2024-08-26T...",
      "modified": "2024-08-26T..."
    }
  ]
}
```

### Tools

#### create_api_key

Create a new API key with model access.

Input:

```json
{
  "project_id": "string (UUID)",
  "name": "string (1-255 chars)",
  "models": ["string", ...]
}
```

Output:

```json
{
  "id": "id",
  "project_id": "uuid",
  "name": "My Key",
  "masked_key": "****abcd",
  "models": ["gpt-4"],
  "created": "2024-08-26T..."
}
```

#### delete_api_key

Revoke and delete an API key.

Input:

```json
{
  "key_id": "string",
  "project_id": "string (UUID)"
}
```

Output:

```
(no content on success)
```

#### rotate_api_key

Generate new credentials for a key.

Input:

```json
{
  "key_id": "string",
  "project_id": "string (UUID)"
}
```

Output:

```json
{
  "id": "id",
  "project_id": "uuid",
  "name": "My Key",
  "masked_key": "****efgh",
  "models": ["gpt-4"],
  "created": "2024-08-26T...",
  "rotated": "2024-08-26T..."
}
```

#### list_api_keys

List all keys for a project.

Input:

```json
{
  "project_id": "string (UUID)"
}
```

Output:

```json
[
  {
    "id": "id",
    "name": "My Key",
    "masked_key": "****abcd",
    "models": ["gpt-4"],
    "created_by": "user@example.com",
    "created": "2024-08-26T...",
    "modified": "2024-08-26T..."
  }
]
```

## Error Handling

The MCP server returns clear error messages:

| Error                   | Cause                                          | Status |
| ----------------------- | ---------------------------------------------- | ------ |
| `MCPAuthorizationError` | User lacks required permission                 | 403    |
| `APIKeyOperationError`  | Policy violation (max keys, invalid name, etc) | 400    |
| `Project not found`     | Invalid project UUID                           | 404    |
| `Key not found`         | Invalid key ID                                 | 404    |

## Audit Logging

All operations are logged to the `mcp_audit_log` table:

```sql
SELECT * FROM mcp_audit_log WHERE user_id = ? ORDER BY timestamp DESC;
```

Columns:

- `timestamp`: When the operation occurred
- `user`: User performing the operation
- `event_type`: PROJECT_READ, KEY_CREATE, KEY_DELETE, etc.
- `resource_type`: project, key, team
- `resource_id`: The affected resource
- `action`: read, create, delete, rotate
- `success`: Whether operation succeeded
- `details`: Sanitized context (counts, names, not secrets)
- `error_message`: Failure reason if unsuccessful
- `ip_address`: Origin IP for security audit

## Testing

```bash
# Run all MCP tests
uv run pytest tests/mcp/ -v

# Run specific test class
uv run pytest tests/mcp/test_auth.py::TestMCPAuthorization -v

# With coverage
uv run pytest tests/mcp/ --cov=mcp
```

Coverage includes:

- Authorization boundary enforcement (14 tests)
- Resource access control (9 tests)
- Tool policy validation (14 tests)
- Error handling and audit logging

## Future Enhancements

- [ ] Real AI Gateway integration (currently placeholder)
- [ ] Rate limiting per user
- [ ] Key expiration policies
- [ ] Webhook notifications on key rotation
- [ ] Compliance reporting views
- [ ] Key usage metrics
- [ ] Automated key rotation schedules

## Troubleshooting

**Server won't start:**

- Ensure Django migrations have run: `python manage.py migrate`
- Check MCP SDK is installed: `pip show mcp`
- Verify user credentials are configured

**Authorization errors:**

- Ensure user has project membership
- Check user role (member vs admin)
- Verify superuser flag for admin operations

**No audit logs:**

- Check database connection
- Verify MCP app is in INSTALLED_APPS
- Inspect Django logs for errors

## Support

For issues or questions:

1. Check the audit logs for operation details
2. Review Django logs for system errors
3. Consult the authorization model documentation
4. File issues with reproducible test cases
