"""Service layer for project membership operations and notifications."""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth.models import Permission
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from simple_history.utils import bulk_create_with_history

from data_platform_app.services import GovUKNotificationError, GovUKNotificationsService
from data_platform_app.utils import build_base_url
from projects.graph import MicrosoftGraphClient
from projects.models import (
    Project,
    ProjectMembership,
    ProjectMembershipPermission,
    ProjectPermission,
)
from users.models import User


class ProjectNotificationError(Exception):
    """Raised when a project membership notification cannot be sent."""


class ProjectMembershipNotificationService:
    """Send project membership emails using GOV.UK Notify templates."""

    def __init__(
        self,
        *,
        notifications_service: GovUKNotificationsService,
        member_added_template_id: str,
        member_removed_template_id: str,
    ) -> None:
        self._notifications_service = notifications_service
        self._member_added_template_id = member_added_template_id
        self._member_removed_template_id = member_removed_template_id

    @classmethod
    def from_settings(cls) -> ProjectMembershipNotificationService:
        """Build a service backed by GOV.UK Notify settings."""
        member_added_template_id = settings.NOTIFY_PROJECT_MEMBER_ADDED_TEMPLATE_ID
        member_removed_template_id = settings.NOTIFY_PROJECT_MEMBER_REMOVED_TEMPLATE_ID

        missing = []
        if not member_added_template_id:
            missing.append("NOTIFY_PROJECT_MEMBER_ADDED_TEMPLATE_ID")
        if not member_removed_template_id:
            missing.append("NOTIFY_PROJECT_MEMBER_REMOVED_TEMPLATE_ID")

        if missing:
            missing_fields = ", ".join(missing)
            raise ImproperlyConfigured(f"Missing Notify settings: {missing_fields}")

        return cls(
            notifications_service=GovUKNotificationsService.from_settings(),
            member_added_template_id=member_added_template_id,
            member_removed_template_id=member_removed_template_id,
        )

    def send_member_added_email(self, *, project, member, added_by) -> None:
        """Send a member-added email to ``member`` for ``project``."""
        if not member.email:
            return

        try:
            project_url = f"{build_base_url(settings.APP_ENV)}{project.get_absolute_url()}"
            self._notifications_service.send_email(
                email_address=member.email,
                template_id=self._member_added_template_id,
                personalisation={
                    "project_name": project.name,
                    "project_description": project.description,
                    "added_by_email": added_by.email,
                    "project_url": project_url,
                },
            )
        except GovUKNotificationError as error:
            raise ProjectNotificationError(str(error)) from error

    def send_member_removed_email(self, *, project, member, removed_by) -> None:
        """Send a member-removed email to ``member`` for ``project``."""
        if not member.email:
            return

        try:
            self._notifications_service.send_email(
                email_address=member.email,
                template_id=self._member_removed_template_id,
                personalisation={
                    "project_name": project.name,
                    "remover_email": removed_by.email,
                },
            )
        except GovUKNotificationError as error:
            raise ProjectNotificationError(str(error)) from error


class ProjectService:
    """Create projects and add their members, resolving Entra selections.

    Selected users who have never signed in are fetched from Microsoft Graph by object id and a
    stub account is created for them::

        with ProjectService.from_request(request) as service:
            project, members = service.create_project(...)
    """

    def __init__(self, request=None, *, graph_client: MicrosoftGraphClient | None = None):
        self._request = request
        self._graph_client = graph_client

    @classmethod
    def from_request(cls, request) -> ProjectService:
        """Build a service that talks to Graph as the signed-in user."""
        return cls(request=request)

    def __enter__(self) -> ProjectService:
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying Graph client if one was created."""
        if self._graph_client is not None:
            self._graph_client.close()

    def create_project(
        self,
        *,
        name: str,
        description: str,
        business_unit_id,
        created_by: User,
        selected_members,
    ) -> tuple[Project, list[User]]:
        """Create a project with its selected members and the owner.

        Returns the project and the members added (owner included) so the
        caller can send notifications. The owner is granted every project
        permission so they are never locked out of managing their own project.
        """
        selections_by_oid = {selection["oid"]: selection for selection in selected_members}
        selections_by_oid[str(created_by.oid)] = {
            "oid": str(created_by.oid),
            "permissions": list(ProjectPermission.values),
        }

        with transaction.atomic():
            project = Project.objects.create(
                name=name,
                description=description,
                business_unit_id=business_unit_id,
                created_by=created_by,
                owner=created_by,
            )
            members = self._add_memberships(
                project, selections_by_oid.values(), added_by=created_by
            )

        return project, members

    def add_members(
        self,
        *,
        project: Project,
        selections,
        added_by: User,
    ) -> list[User]:
        """Add selected members to ``project`` and return the members added."""
        with transaction.atomic():
            members = self._add_memberships(project, selections, added_by=added_by)

        return members

    def _add_memberships(self, project: Project, selections, *, added_by: User) -> list[User]:
        """Create memberships and their granted permissions for ``selections``.

        ``selections`` are dicts with an ``oid`` and a ``permissions`` list of
        ``ProjectPermission`` codenames (possibly empty).
        """
        selections = list(selections)
        members = self._resolve_members(selections)
        permissions_by_codename = self._permissions_by_codename()

        memberships = []
        for member, selection in zip(members, selections, strict=True):
            membership, _ = ProjectMembership.objects.get_or_create(project=project, user=member)
            memberships.append((membership, selection.get("permissions") or []))

        permission_rows = [
            ProjectMembershipPermission(
                membership=membership,
                permission=permissions_by_codename[codename],
                granted_by=added_by,
            )
            for membership, codenames in memberships
            for codename in codenames
            if codename in permissions_by_codename
        ]
        if permission_rows:
            bulk_create_with_history(
                permission_rows,
                ProjectMembershipPermission,
                ignore_conflicts=True,
                default_user=added_by,
            )

        return members

    def _permissions_by_codename(self) -> dict[str, Permission]:
        """Return the ``projects.Project`` permissions, keyed by codename."""
        return {
            permission.codename: permission
            for permission in Permission.objects.filter(
                content_type__app_label="projects",
                content_type__model="project",
                codename__in=ProjectPermission.values,
            )
        }

    def _resolve_members(self, selections) -> list[User]:
        """Resolve cleaned selections to users, creating stubs for new oids.

        Selections come from the formset, which has already validated,
        de-duplicated, and ordered the oids, so only oids without a local user
        trigger a Graph call.
        """
        oids = [selection["oid"] for selection in selections]
        existing = {str(user.oid): user for user in User.objects.filter(oid__in=oids)}
        return [
            existing[oid] if oid in existing else self._create_user_from_graph(oid) for oid in oids
        ]

    def _create_user_from_graph(self, oid: str) -> User:
        graph_user = self._get_graph_client().get_user(oid)
        user, _ = User.objects.get_or_create(
            oid=graph_user["id"],
            defaults={
                "email": (graph_user.get("mail") or "").strip(),
                "first_name": graph_user.get("givenName") or "",
                "last_name": graph_user.get("surname") or "",
                "username": graph_user.get("displayName") or "",
            },
        )
        return user

    def _get_graph_client(self) -> MicrosoftGraphClient:
        if self._graph_client is None:
            self._graph_client = MicrosoftGraphClient.from_request(self._request)
        return self._graph_client

    def update_member_permissions(
        self,
        *,
        membership: ProjectMembership,
        permission_codenames: list[str],
        updated_by: User,
    ) -> None:
        """Update the permissions granted to an existing project member."""
        with transaction.atomic():
            membership = ProjectMembership.objects.select_for_update().get(pk=membership.pk)
            requested = set(permission_codenames)
            existing = set(
                membership.permissions.values_list(
                    "permission__codename",
                    flat=True,
                )
            )

            to_add = requested - existing
            to_remove = existing - requested

            if not to_add and not to_remove:
                return

            permissions_by_codename = self._permissions_by_codename()
            if to_remove:
                membership.permissions.filter(
                    permission__codename__in=to_remove,
                ).delete()

            permission_rows = [
                ProjectMembershipPermission(
                    membership=membership,
                    permission=permissions_by_codename[codename],
                    granted_by=updated_by,
                )
                for codename in to_add
            ]

            if permission_rows:
                bulk_create_with_history(
                    permission_rows,
                    ProjectMembershipPermission,
                    default_user=updated_by,
                )
