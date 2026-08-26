"""Audit logging for MCP operations.

All audit events are written to the Python logger as structured log records.
No database table is required — the audit trail is captured by whatever log
handler the deployment configures (e.g. stdout → Fluentd → Kibana in
production, or the Django test log capture in tests).
"""

import logging
from typing import Any

from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)
User = get_user_model()


class MCPAuditEventType:
    """Audit event type constants."""

    PROJECT_READ = "project_read"
    TEAM_READ = "team_read"
    KEY_READ = "key_read"
    KEY_CREATE = "key_create"
    KEY_DELETE = "key_delete"
    KEY_ROTATE = "key_rotate"
    AUTH_FAILURE = "auth_failure"
    AUTH_SUCCESS = "auth_success"


class MCPAuditor:
    """Handles audit logging for MCP operations."""

    def __init__(self, user=None, ip_address: str | None = None):
        """Initialise auditor.

        Args:
            user: The user performing the operation
            ip_address: IP address of the request origin
        """
        self.user = user
        self.ip_address = ip_address

    def log_event(
        self,
        event_type: str,
        resource_type: str,
        resource_id: str,
        action: str,
        success: bool = True,
        details: dict[str, Any] | None = None,
        error_message: str = "",
    ) -> None:
        """Log an audit event to the Python logger.

        Args:
            event_type: Type of event (use MCPAuditEventType constants)
            resource_type: Type of resource affected (project, key, team)
            resource_id: ID of the affected resource
            action: Specific action performed (create, read, delete, rotate)
            success: Whether the operation succeeded
            details: Additional context (must not contain sensitive data)
            error_message: Error message if operation failed
        """
        sanitized_details = dict(details or {})
        for sensitive_key in ("secret", "key", "token"):
            if sensitive_key in sanitized_details:
                sanitized_details[sensitive_key] = "***REDACTED***"

        log_level = logging.INFO if success else logging.WARNING
        logger.log(
            log_level,
            "MCP audit: %s - %s on %s:%s",
            event_type,
            action,
            resource_type,
            resource_id,
            extra={
                "user_id": self.user.id if self.user else None,
                "user_email": self.user.email if self.user else None,
                "event_type": event_type,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "action": action,
                "success": success,
                "details": sanitized_details,
                "error_message": error_message,
                "ip_address": self.ip_address,
            },
        )

    def log_project_read(self, project_id: str, success: bool = True, details: dict[str, Any] | None = None) -> None:
        """Log a project data read operation."""
        self.log_event(MCPAuditEventType.PROJECT_READ, "project", project_id, "read", success, details)

    def log_team_read(self, team_id: str, success: bool = True, details: dict[str, Any] | None = None) -> None:
        """Log a team data read operation."""
        self.log_event(MCPAuditEventType.TEAM_READ, "team", team_id, "read", success, details)

    def log_key_read(self, key_id: str, project_id: str, success: bool = True, details: dict[str, Any] | None = None) -> None:
        """Log an API key read operation."""
        self.log_event(MCPAuditEventType.KEY_READ, "key", key_id, "read", success, {**(details or {}), "project_id": project_id})

    def log_key_create(self, key_id: str, project_id: str, key_name: str, models: list[str], success: bool = True, error_message: str = "") -> None:
        """Log an API key creation operation."""
        self.log_event(
            MCPAuditEventType.KEY_CREATE, "key", key_id, "create", success,
            {"project_id": project_id, "key_name": key_name, "models_count": len(models)},
            error_message,
        )

    def log_key_delete(self, key_id: str, project_id: str, key_name: str, success: bool = True, error_message: str = "") -> None:
        """Log an API key deletion operation."""
        self.log_event(
            MCPAuditEventType.KEY_DELETE, "key", key_id, "delete", success,
            {"project_id": project_id, "key_name": key_name},
            error_message,
        )

    def log_key_rotate(self, key_id: str, project_id: str, key_name: str, success: bool = True, error_message: str = "") -> None:
        """Log an API key rotation operation."""
        self.log_event(
            MCPAuditEventType.KEY_ROTATE, "key", key_id, "rotate", success,
            {"project_id": project_id, "key_name": key_name},
            error_message,
        )
