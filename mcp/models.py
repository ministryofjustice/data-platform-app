"""Audit logging for MCP operations.

Records all MCP operations for security and compliance.
"""

import logging
from typing import Any

from django.contrib.auth import get_user_model
from django.db import models

logger = logging.getLogger(__name__)
User = get_user_model()


class MCPAuditEventType(models.TextChoices):
    """Types of MCP audit events."""

    PROJECT_READ = "project_read", "Project data read"
    TEAM_READ = "team_read", "Team data read"
    KEY_READ = "key_read", "API key data read"
    KEY_CREATE = "key_create", "API key created"
    KEY_DELETE = "key_delete", "API key deleted"
    KEY_ROTATE = "key_rotate", "API key rotated"
    AUTH_FAILURE = "auth_failure", "Authorization check failed"
    AUTH_SUCCESS = "auth_success", "Authorization check passed"


class MCPAuditLog(models.Model):
    """Audit log entry for MCP operations."""

    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="mcp_audit_logs",
    )
    event_type = models.CharField(
        max_length=50,
        choices=MCPAuditEventType.choices,
    )
    resource_type = models.CharField(
        max_length=50,
        help_text="Type of resource affected (project, key, team)",
    )
    resource_id = models.CharField(
        max_length=255,
        help_text="ID of the affected resource",
    )
    action = models.CharField(
        max_length=50,
        help_text="Specific action performed (create, read, delete, rotate)",
    )
    success = models.BooleanField(
        default=True,
        help_text="Whether the operation succeeded",
    )
    details = models.JSONField(
        default=dict,
        help_text="Additional context (sanitized, no sensitive data)",
    )
    error_message = models.TextField(
        blank=True,
        help_text="Error message if operation failed",
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="IP address of the requester",
    )

    class Meta:
        db_table = "mcp_audit_log"
        indexes = [
            models.Index(fields=["timestamp", "user"]),
            models.Index(fields=["event_type", "timestamp"]),
            models.Index(fields=["resource_type", "resource_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.event_type} by {self.user} at {self.timestamp}"


class MCPAuditor:
    """Handles audit logging for MCP operations."""

    def __init__(
        self,
        user: User | None = None,
        ip_address: str | None = None,
    ):
        """Initialize auditor.

        Args:
            user: The user performing the operation
            ip_address: IP address of the request origin
        """
        self.user = user
        self.ip_address = ip_address

    def log_event(
        self,
        event_type: MCPAuditEventType,
        resource_type: str,
        resource_id: str,
        action: str,
        success: bool = True,
        details: dict[str, Any] | None = None,
        error_message: str = "",
    ) -> MCPAuditLog:
        """Log an audit event.

        Args:
            event_type: Type of event
            resource_type: Type of resource affected
            resource_id: ID of the affected resource
            action: Specific action performed
            success: Whether the operation succeeded
            details: Additional context (must not contain sensitive data)
            error_message: Error message if operation failed

        Returns:
            The created MCPAuditLog object
        """
        # Sanitize details - ensure no sensitive data
        sanitized_details = details or {}
        if "secret" in sanitized_details:
            sanitized_details["secret"] = "***REDACTED***"
        if "key" in sanitized_details:
            sanitized_details["key"] = "***REDACTED***"
        if "token" in sanitized_details:
            sanitized_details["token"] = "***REDACTED***"

        audit_log = MCPAuditLog.objects.create(
            user=self.user,
            event_type=event_type,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            success=success,
            details=sanitized_details,
            error_message=error_message,
            ip_address=self.ip_address,
        )

        log_level = logging.INFO if success else logging.WARNING
        logger.log(
            log_level,
            f"MCP audit: {event_type} - {action} on {resource_type}:{resource_id}",
            extra={
                "user_id": self.user.id if self.user else None,
                "event_type": event_type,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "action": action,
                "success": success,
                "details": sanitized_details,
            },
        )

        return audit_log

    def log_project_read(
        self,
        project_id: str,
        success: bool = True,
        details: dict[str, Any] | None = None,
    ) -> MCPAuditLog:
        """Log a project data read operation."""
        return self.log_event(
            event_type=MCPAuditEventType.PROJECT_READ,
            resource_type="project",
            resource_id=project_id,
            action="read",
            success=success,
            details=details,
        )

    def log_team_read(
        self,
        team_id: str,
        success: bool = True,
        details: dict[str, Any] | None = None,
    ) -> MCPAuditLog:
        """Log a team data read operation."""
        return self.log_event(
            event_type=MCPAuditEventType.TEAM_READ,
            resource_type="team",
            resource_id=team_id,
            action="read",
            success=success,
            details=details,
        )

    def log_key_read(
        self,
        key_id: str,
        project_id: str,
        success: bool = True,
        details: dict[str, Any] | None = None,
    ) -> MCPAuditLog:
        """Log an API key read operation."""
        return self.log_event(
            event_type=MCPAuditEventType.KEY_READ,
            resource_type="key",
            resource_id=key_id,
            action="read",
            success=success,
            details={**(details or {}), "project_id": project_id},
        )

    def log_key_create(
        self,
        key_id: str,
        project_id: str,
        key_name: str,
        models: list[str],
        success: bool = True,
        error_message: str = "",
    ) -> MCPAuditLog:
        """Log an API key creation operation."""
        return self.log_event(
            event_type=MCPAuditEventType.KEY_CREATE,
            resource_type="key",
            resource_id=key_id,
            action="create",
            success=success,
            details={
                "project_id": project_id,
                "key_name": key_name,
                "models_count": len(models),
            },
            error_message=error_message,
        )

    def log_key_delete(
        self,
        key_id: str,
        project_id: str,
        key_name: str,
        success: bool = True,
        error_message: str = "",
    ) -> MCPAuditLog:
        """Log an API key deletion operation."""
        return self.log_event(
            event_type=MCPAuditEventType.KEY_DELETE,
            resource_type="key",
            resource_id=key_id,
            action="delete",
            success=success,
            details={
                "project_id": project_id,
                "key_name": key_name,
            },
            error_message=error_message,
        )

    def log_key_rotate(
        self,
        key_id: str,
        project_id: str,
        key_name: str,
        success: bool = True,
        error_message: str = "",
    ) -> MCPAuditLog:
        """Log an API key rotation operation."""
        return self.log_event(
            event_type=MCPAuditEventType.KEY_ROTATE,
            resource_type="key",
            resource_id=key_id,
            action="rotate",
            success=success,
            details={
                "project_id": project_id,
                "key_name": key_name,
            },
            error_message=error_message,
        )

    def log_auth_success(
        self,
        operation: str,
        resource_type: str,
        resource_id: str,
    ) -> MCPAuditLog:
        """Log a successful authorization check."""
        return self.log_event(
            event_type=MCPAuditEventType.AUTH_SUCCESS,
            resource_type=resource_type,
            resource_id=resource_id,
            action=operation,
            success=True,
        )

    def log_auth_failure(
        self,
        operation: str,
        resource_type: str,
        resource_id: str,
        error_message: str,
    ) -> MCPAuditLog:
        """Log a failed authorization check."""
        return self.log_event(
            event_type=MCPAuditEventType.AUTH_FAILURE,
            resource_type=resource_type,
            resource_id=resource_id,
            action=operation,
            success=False,
            error_message=error_message,
        )
