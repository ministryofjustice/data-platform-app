"""Tools for API key lifecycle management.

Handles creation, deletion, rotation, and listing of API keys with policy checks
and comprehensive audit logging.
"""

import logging
from typing import Optional

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction

from ai_gateway.models import Key, Team
from mcp.auth import MCPAuthorization, MCPAuthorizationError
from mcp.models import MCPAuditor

logger = logging.getLogger(__name__)
User = get_user_model()


class APIKeyOperationError(Exception):
    """Raised when an API key operation fails."""

    pass


class APIKeyManager:
    """Manages API key lifecycle operations with policy enforcement."""

    # Policy constants
    MAX_KEYS_PER_PROJECT = 10
    VALID_MODEL_PATTERN = r"^[a-zA-Z0-9\-_.]+$"

    def __init__(self, user: User, ip_address: Optional[str] = None):
        """Initialize manager with user context.
        
        Args:
            user: The authenticated user
            ip_address: IP address of the request origin
        """
        self.user = user
        self.auth = MCPAuthorization(user)
        self.auditor = MCPAuditor(user=user, ip_address=ip_address)

    def create_key(
        self,
        project_id: str,
        name: str,
        models: list[str],
    ) -> dict:
        """Create a new API key.
        
        Args:
            project_id: UUID of the project
            name: Name for the key
            models: List of model IDs to grant access to
            
        Returns:
            Dictionary with key details (excluding secret)
            
        Raises:
            MCPAuthorizationError: If user lacks permission
            APIKeyOperationError: If operation fails
        """
        try:
            # Authorization: must be project admin
            project = self.auth.authorize_key_creation(project_id)
            
            # Validation
            if not name or len(name) > 255:
                raise ValidationError("Key name must be 1-255 characters")
            
            if not models or len(models) == 0:
                raise ValidationError("At least one model must be specified")
            
            if len(models) > 50:
                raise ValidationError("Maximum 50 models per key")
            
            # Policy check: max keys per project
            existing_key_count = Key.objects.filter(project=project).count()
            if existing_key_count >= self.MAX_KEYS_PER_PROJECT:
                raise APIKeyOperationError(
                    f"Project has reached maximum of {self.MAX_KEYS_PER_PROJECT} keys"
                )
            
            # Check for duplicate name in project
            if Key.objects.filter(project=project, name=name).exists():
                raise APIKeyOperationError(
                    f"Key name '{name}' already exists in this project"
                )
            
            # Create the key using AI Gateway client
            # TODO: Call AI Gateway API to create key
            # For now, we'll create a placeholder that demonstrates the flow
            
            key = Key.objects.create(
                project=project,
                name=name,
                litellm_secret="placeholder_secret",  # Would come from AI Gateway
                litellm_alias=f"{project.uuid}_{name}",
                litellm_token="placeholder_token",
                masked_key="***masked",
                created_by=self.user,
                models=models,
            )
            
            # Audit log
            self.auditor.log_key_create(
                key_id=str(key.id),
                project_id=project_id,
                key_name=name,
                models=models,
                success=True,
            )
            
            logger.info(
                "API key created",
                extra={
                    "user_id": self.user.id,
                    "key_id": key.id,
                    "project_id": project_id,
                    "key_name": name,
                    "model_count": len(models),
                },
            )
            
            return {
                "id": str(key.id),
                "project_id": project_id,
                "name": key.name,
                "masked_key": key.masked_key,
                "models": key.models,
                "created": key.created.isoformat(),
            }
            
        except MCPAuthorizationError:
            self.auditor.log_key_create(
                key_id="unknown",
                project_id=project_id,
                key_name=name,
                models=models,
                success=False,
                error_message="Authorization denied",
            )
            raise
        except (ValidationError, APIKeyOperationError) as e:
            self.auditor.log_key_create(
                key_id="unknown",
                project_id=project_id,
                key_name=name,
                models=models,
                success=False,
                error_message=str(e),
            )
            raise APIKeyOperationError(str(e)) from e

    def delete_key(self, key_id: str, project_id: str) -> None:
        """Delete an API key.
        
        Args:
            key_id: ID of the key to delete
            project_id: UUID of the project
            
        Raises:
            MCPAuthorizationError: If user lacks permission
            APIKeyOperationError: If operation fails
        """
        try:
            # Authorization: must be project admin
            project = self.auth.authorize_key_deletion(project_id)
            
            # Get the key
            try:
                key = Key.objects.get(id=key_id, project=project)
            except Key.DoesNotExist:
                raise APIKeyOperationError(f"Key {key_id} not found in project")
            
            key_name = key.name
            
            # Delete from AI Gateway
            # TODO: Call AI Gateway API to delete key
            
            with transaction.atomic():
                key.delete()
            
            # Audit log
            self.auditor.log_key_delete(
                key_id=key_id,
                project_id=project_id,
                key_name=key_name,
                success=True,
            )
            
            logger.info(
                "API key deleted",
                extra={
                    "user_id": self.user.id,
                    "key_id": key_id,
                    "project_id": project_id,
                    "key_name": key_name,
                },
            )
            
        except MCPAuthorizationError:
            self.auditor.log_key_delete(
                key_id=key_id,
                project_id=project_id,
                key_name="unknown",
                success=False,
                error_message="Authorization denied",
            )
            raise
        except APIKeyOperationError as e:
            self.auditor.log_key_delete(
                key_id=key_id,
                project_id=project_id,
                key_name="unknown",
                success=False,
                error_message=str(e),
            )
            raise

    def rotate_key(self, key_id: str, project_id: str) -> dict:
        """Rotate an API key (generate new secret).
        
        Args:
            key_id: ID of the key to rotate
            project_id: UUID of the project
            
        Returns:
            Dictionary with updated key details (excluding secret)
            
        Raises:
            MCPAuthorizationError: If user lacks permission
            APIKeyOperationError: If operation fails
        """
        try:
            # Authorization: must be project admin
            project = self.auth.authorize_key_rotation(project_id)
            
            # Get the key
            try:
                key = Key.objects.get(id=key_id, project=project)
            except Key.DoesNotExist:
                raise APIKeyOperationError(f"Key {key_id} not found in project")
            
            # Rotate the key in AI Gateway
            # TODO: Call AI Gateway API to rotate key
            # Would update litellm_secret and litellm_token
            
            key.litellm_secret = "rotated_secret_placeholder"
            key.litellm_token = "rotated_token_placeholder"
            key.save()
            
            # Audit log
            self.auditor.log_key_rotate(
                key_id=key_id,
                project_id=project_id,
                key_name=key.name,
                success=True,
            )
            
            logger.info(
                "API key rotated",
                extra={
                    "user_id": self.user.id,
                    "key_id": key_id,
                    "project_id": project_id,
                },
            )
            
            return {
                "id": str(key.id),
                "project_id": project_id,
                "name": key.name,
                "masked_key": key.masked_key,
                "models": key.models,
                "created": key.created.isoformat(),
                "rotated": key.modified.isoformat(),
            }
            
        except MCPAuthorizationError:
            self.auditor.log_key_rotate(
                key_id=key_id,
                project_id=project_id,
                key_name="unknown",
                success=False,
                error_message="Authorization denied",
            )
            raise
        except APIKeyOperationError as e:
            self.auditor.log_key_rotate(
                key_id=key_id,
                project_id=project_id,
                key_name="unknown",
                success=False,
                error_message=str(e),
            )
            raise

    def list_keys(self, project_id: str) -> list[dict]:
        """List API keys for a project.
        
        Args:
            project_id: UUID of the project
            
        Returns:
            List of key details (excluding secrets)
            
        Raises:
            MCPAuthorizationError: If user lacks permission
        """
        try:
            # Authorization: must have access to project
            project = self.auth.authorize_project_access(project_id)
            
            keys = Key.objects.filter(project=project).select_related("created_by")
            
            keys_data = [
                {
                    "id": str(key.id),
                    "name": key.name,
                    "masked_key": key.masked_key,
                    "models": key.models,
                    "created_by": key.created_by.email if key.created_by else None,
                    "created": key.created.isoformat(),
                    "modified": key.modified.isoformat(),
                }
                for key in keys
            ]
            
            logger.info(
                "API keys listed",
                extra={
                    "user_id": self.user.id,
                    "project_id": project_id,
                    "key_count": len(keys_data),
                },
            )
            
            return keys_data
            
        except MCPAuthorizationError:
            raise
