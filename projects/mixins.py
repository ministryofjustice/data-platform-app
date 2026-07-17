from django.shortcuts import get_object_or_404

ADD_USER_SESSION_KEY = "project_user_add_selection"
PROJECT_CREATE_SESSION_KEY = "project_create"
USER_BUCKET_SESSION_KEY = "project_create_user_add"


class ProjectUserSelectionSessionMixin:
    def get_project(self):
        return None

    def get_user_bucket_key(self):
        raise NotImplementedError

    def get_selected_user_ids(self):
        session_map = self.request.session.get(ADD_USER_SESSION_KEY, {})
        return [int(user_id) for user_id in session_map.get(self.get_user_bucket_key(), [])]

    def set_selected_user_ids(self, user_ids):
        session_map = self.request.session.get(ADD_USER_SESSION_KEY, {})
        session_map[self.get_user_bucket_key()] = list(user_ids)
        self.request.session[ADD_USER_SESSION_KEY] = session_map

    def clear_selected_user_ids(self):
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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["success_message"] = self.request.session.pop("success_message", None)
        context["active_project_section"] = self.active_project_section
        return context
