# MCP Server Implementation Notes

## Architecture Overview

The MCP server is built as a Django app that provides two main capabilities:

1. **Read-Only Resources**: Operational data access (projects, teams, keys)
2. **Admin Tools**: API key lifecycle management (create, delete, rotate)

### Component Structure

```
mcp/
├── auth.py              # Authorization checks (MCPAuthorization)
├── models.py            # Audit logging (MCPAuditLog, MCPAuditor)
├── resources.py         # Data access (OperationalDataReader)
├── tools.py             # Key lifecycle (APIKeyManager)
├── server.py            # MCP server wrapper (DataPlatformMCPServer)
├── management/
│   └── commands/
│       └── mcp.py       # Django management command
└── README.md            # User documentation
```

## Key Design Decisions

### 1. Authorization Strategy

**Explicit Permission Checks**

- Every operation calls `MCPAuthorization.authorize_*()`
- Raises `MCPAuthorizationError` on denial
- Logged immediately for audit trail

**Superuser Bypass**

- Superusers automatically see all projects
- No explicit membership needed
- Special handling in `authorize_project_access()`

**Role-Based Access Control**

- Two roles: `admin`, `member`
- Enforced via `ProjectUserPermissions` model
- Tools require `admin` role
- Resources allow both roles

### 2. Audit Logging Strategy

**Sanitization First**

- MCPAuditor automatically removes sensitive fields
- Redacted fields: `secret`, `key`, `token`
- Details stored as JSON for querying

**Dual Logging**

- Django logger for real-time monitoring
- MCPAuditLog model for compliance queries
- Includes IP address for security audit

**Immutable Records**

- Audit logs are never updated/deleted
- All writes through MCPAuditor class
- Consistent timestamp across all entries

### 3. Data Protection Strategy

**Secrets Never Exposed**

- Resources return `masked_key` only (e.g., `***abcd`)
- `litellm_secret` and `litellm_token` excluded from serialization
- Tools return masked keys after creation

**Encryption at Rest**

- Uses Django's `EncryptedTextField` from `ai_gateway.fields`
- Fernet cipher with rotating keys support
- Already configured in project settings

### 4. Policy Enforcement Strategy

**Per-Project Limits**

- Maximum 10 keys per project (configurable via `APIKeyManager.MAX_KEYS_PER_PROJECT`)
- Prevents resource exhaustion

**Uniqueness Constraints**

- Key names must be unique within a project
- Prevents confusion in UI/logs

**Model Access Validation**

- At least 1 model required
- Maximum 50 models per key
- Models must match valid format (alphanumeric + dash/underscore)

## Integration Points

### Django Models Used

1. **User Model** (`users.User`)
   - Identified by `oid` (Entra ID)
   - `is_superuser` flag for admin bypass
   - Email for audit context

2. **Project Model** (`projects.Project`)
   - UUID primary key for MCP resources
   - Created_by tracking for audit

3. **ProjectUserPermissions** (`projects.ProjectUserPermissions`)
   - Through model for user-project membership
   - Role field: `admin` or `member`

4. **AI Gateway Models** (`ai_gateway.models`)
   - `Team`: One per project, links to AI Gateway
   - `Key`: API keys with Fernet-encrypted secret

### External Services

**AI Gateway**

- **Current**: Placeholder in `tools.py`
- **TODO**: Implement actual API calls
- **Methods needed**:
  - POST `/keys` - Create key
  - DELETE `/keys/{id}` - Revoke key
  - PATCH `/keys/{id}` - Rotate key
  - GET `/teams/{id}/keys` - List keys

## Testing Strategy

### Test Organization

```
tests/mcp/
├── test_auth.py         # 14 tests for authorization
├── test_resources.py    # 9 tests for data access
└── test_tools.py        # 14 tests for key lifecycle
```

### Test Database

- Uses SQLite in-memory for speed
- Configured in `data_platform_app/settings/test.py`
- No PostgreSQL dependency needed

### Coverage Targets

- Auth module: 95%+ coverage
- Resources: 90%+ coverage
- Tools: 88%+ coverage
- Audit logging verified via tool tests

## Future Enhancement Opportunities

### 1. AI Gateway Integration (CRITICAL)

```python
# Replace placeholders in tools.py:create_key()
from ai_gateway.client import AIGatewayClient

client = AIGatewayClient.from_settings()
response = client.create_key(
    team_id=team.litellm_team_id,
    name=name,
    models=models,
)
key.litellm_secret = response["secret"]
key.litellm_token = response["token"]
key.litellm_alias = response["alias"]
```

### 2. Rate Limiting

```python
# Add to APIKeyManager or resources.py
from django.core.cache import cache
from django.utils.timezone import now, timedelta


def check_rate_limit(user_id, operation, limit_per_min=10):
    key = f"mcp:{user_id}:{operation}"
    count = cache.get(key, 0)
    if count >= limit_per_min:
        raise APIKeyOperationError("Rate limit exceeded")
    cache.set(key, count + 1, 60)
```

### 3. Key Expiration Policies

```python
# Add to Key model
from django.utils import timezone
from datetime import timedelta


class Key(Model):
    expires_at = models.DateTimeField(null=True, blank=True)

    def is_expired(self):
        if not self.expires_at:
            return False
        return timezone.now() >= self.expires_at

    def days_until_expiry(self):
        if not self.expires_at:
            return None
        delta = self.expires_at - timezone.now()
        return delta.days
```

### 4. Webhook Notifications

```python
# Notify external systems of key changes
from django.dispatch import Signal

key_created = Signal()
key_deleted = Signal()
key_rotated = Signal()

# In tools.py:
key_created.send(
    sender=APIKeyManager,
    key=key,
    user=self.user,
)
```

### 5. Usage Metrics

```python
# Track key usage for billing/analysis
class KeyUsageMetric(Model):
    key = ForeignKey(Key)
    timestamp = DateTimeField(auto_now_add=True)
    request_count = IntegerField()
    error_count = IntegerField()
```

## Security Considerations

### Input Validation

- All user inputs validated before use
- Model lists limited to 50 items
- Key names limited to 255 chars
- Project UUIDs validated

### SQL Injection Prevention

- All queries use Django ORM
- No raw SQL in MCP code
- Parameterized queries for all lookups

### Privilege Escalation Prevention

- No direct superuser flag modification
- All admin operations checked
- Role upgrades only via explicit methods

### Information Disclosure Prevention

- No stack traces in error messages
- Sensitive fields excluded from resources
- Audit logs sanitized

### Denial of Service Prevention

- Rate limiting placeholder prepared
- Key creation count enforced
- Query optimization with select_related

## Troubleshooting Guide

### Common Issues

**"User does not have access to project"**

- Check ProjectUserPermissions entry
- Verify user's role is `admin` for creation/deletion
- Superusers bypass this check

**"Key not found in project"**

- Verify key exists: `Key.objects.get(id=key_id, project_id=...)`
- Check key wasn't already deleted
- Ensure project_id matches

**Audit logs not appearing**

- Check Django logging configuration
- Verify MCPAuditLog model created (migrations run)
- Check database connection

**Authorization errors in tests**

- Ensure `@pytest.mark.django_db` decorator present
- Create ProjectUserPermissions for test users
- Add `db` fixture to test methods

## Performance Optimization Notes

### Current Status

- O(1) lookups for projects (by UUID)
- O(n) for key listing (acceptable for <100 keys/project)
- Minimal queries with select_related/prefetch_related

### Future Optimizations

```python
# Use select_related to avoid N+1 queries
keys = Key.objects.filter(project__in=projects).select_related("project", "created_by")

# Use prefetch_related for reverse relations
projects = Project.objects.prefetch_related(
    "user_permissions__user",
    "ai_gateway_keys",
)


# Add database indexes for audit queries
class Meta:
    indexes = [
        models.Index(fields=["timestamp", "user"]),
        models.Index(fields=["event_type", "timestamp"]),
    ]
```

## Deployment Checklist

- [ ] MCP SDK installed (check pyproject.toml)
- [ ] Migrations run: `python manage.py migrate`
- [ ] AI Gateway client integrated (replace placeholders)
- [ ] Rate limiting configured (add to settings)
- [ ] Audit log retention policy set
- [ ] SSL/TLS configured for production
- [ ] Logging/monitoring setup
- [ ] Backup strategy for audit logs
- [ ] User onboarding documentation
- [ ] Load testing completed

## Maintenance

### Regular Tasks

1. Monitor audit log table size (archive old logs monthly)
2. Review authorization denials for patterns
3. Validate key usage aligns with access
4. Update dependencies quarterly

### Emergency Procedures

1. Key compromise: Rotate immediately via `rotate_api_key`
2. Audit log corruption: Restore from backup
3. Authorization system failure: Fall back to Django admin
4. User access revocation: Remove ProjectUserPermissions entry

## Code Style & Conventions

- Type hints on all functions
- Docstrings following Google style
- Error messages include context
- Logging at INFO for success, WARNING for failures
- No print() statements (use logging)
- Transaction handling for data mutations

## References

- MCP Specification: https://modelcontextprotocol.io
- Django Documentation: https://docs.djangoproject.com
- Python type hints: https://www.python.org/dev/peps/pep-0484/
- MOJ Security Standards: See .github/instructions/
