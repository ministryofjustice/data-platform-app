import sentry_sdk
from django.core.exceptions import ImproperlyConfigured
from django.shortcuts import get_object_or_404

from projects.services import ProjectMembershipNotificationService, ProjectNotificationError

ADD_USER_SESSION_KEY = "project_user_add_selection"
PROJECT_CREATE_SESSION_KEY = "project_create"
USER_BUCKET_SESSION_KEY = "project_create_user_add"


class ProjectUserSelectionSessionMixin:
    def get_project(self):
        return None

    def get_user_bucket_key(self):
        raise NotImplementedError

    def get_selected_members(self):
        session_map = self.request.session.get(ADD_USER_SESSION_KEY, {})
        return list(session_map.get(self.get_user_bucket_key(), []))

    def set_selected_members(self, members):
        session_map = self.request.session.get(ADD_USER_SESSION_KEY, {})
        session_map[self.get_user_bucket_key()] = list(members)
        self.request.session[ADD_USER_SESSION_KEY] = session_map

    def clear_selected_members(self):
        session_map = self.request.session.get(ADD_USER_SESSION_KEY, {})
        session_map.pop(self.get_user_bucket_key(), None)
        self.request.session[ADD_USER_SESSION_KEY] = session_map


class ExistingProjectMixin:
    def get_project(self):
        from projects.models import Project

        if not hasattr(self, "_project"):
            self._project = get_object_or_404(
                Project.objects.filter(
                    user_permissions__user=self.request.user,
                    user_permissions__role="admin",
                ).distinct(),
                uuid=self.kwargs["uuid"],
            )
        return self._project

    def get_user_bucket_key(self):
        return f"project:{self.get_project().id}"


class UUIDObjectMixin:
    """Mixin for DetailView subclasses that use UUID as the URL identifier."""

    def get_object(self, queryset=None):
        if queryset is None:
            queryset = self.get_queryset()
        return get_object_or_404(queryset, uuid=self.kwargs["uuid"])


class ProjectLayoutContextMixin:
    active_project_section = None
    active_ai_gateway_section = None

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["success_message"] = self.request.session.pop("success_message", None)
        context["active_project_section"] = self.active_project_section
        context["active_ai_gateway_section"] = self.active_ai_gateway_section
        return context


class ProjectMembershipNotificationMixin:
    """Best-effort membership notification helpers for project views."""

    @staticmethod
    def get_notification_service():
        try:
            return ProjectMembershipNotificationService.from_settings()
        except ImproperlyConfigured as error:
            sentry_sdk.capture_exception(error)
            return None

    def send_member_added_notifications(self, *, project, members, added_by) -> None:
        notification_service = self.get_notification_service()
        if notification_service is None:
            return

        for member in members:
            try:
                notification_service.send_member_added_email(
                    project=project,
                    member=member,
                    added_by=added_by,
                )
            except ProjectNotificationError as error:
                sentry_sdk.capture_exception(error)

    def send_member_removed_notification(self, *, project, member, removed_by) -> None:
        notification_service = self.get_notification_service()
        if notification_service is None:
            return

        try:
            notification_service.send_member_removed_email(
                project=project,
                member=member,
                removed_by=removed_by,
            )
        except ProjectNotificationError as error:
            sentry_sdk.capture_exception(error)
