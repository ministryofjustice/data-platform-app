import sentry_sdk
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Prefetch
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views.generic.base import View
from django.views.generic.detail import DetailView
from django.views.generic.edit import DeleteView, FormView
from django.views.generic.list import ListView

from ai_gateway.exceptions import AIGatewayError
from ai_gateway.models import Team
from ai_gateway.services import KeyService
from projects.forms import (
    ProjectCreateAddUsersDecisionForm,
    ProjectCreateForm,
    build_project_add_member_formset,
)
from projects.graph import (
    EntraAuthenticationError,
    EntraDirectoryError,
    EntraRequestError,
    MicrosoftGraphClient,
)
from projects.mixins import (
    ADD_USER_SESSION_KEY,
    PROJECT_CREATE_SESSION_KEY,
    USER_BUCKET_SESSION_KEY,
    ExistingProjectMixin,
    ProjectLayoutContextMixin,
    ProjectMembershipNotificationMixin,
    ProjectUserSelectionSessionMixin,
    UUIDObjectMixin,
)
from projects.models import BusinessUnit, Project, ProjectUserPermissions
from projects.services import ProjectService


def clear_project_create_session(request):
    request.session.pop(PROJECT_CREATE_SESSION_KEY, None)

    session_map = request.session.get(ADD_USER_SESSION_KEY, {})
    session_map.pop(USER_BUCKET_SESSION_KEY, None)
    if session_map:
        request.session[ADD_USER_SESSION_KEY] = session_map
    else:
        request.session.pop(ADD_USER_SESSION_KEY, None)


class EntraUserSearchView(LoginRequiredMixin, View):
    """Search the Entra tenant for users, on behalf of the signed-in user.

    Returns a small JSON representation so the member-picker autocomplete never
    receives raw Microsoft Graph objects or the delegated bearer token.
    """

    MIN_QUERY_LENGTH = 3
    MAX_QUERY_LENGTH = 256
    RESULT_LIMIT = 10

    def get(self, request, *args, **kwargs):
        query = request.GET.get("q", "").strip()
        if len(query) < self.MIN_QUERY_LENGTH:
            return JsonResponse({"results": []})
        query = query[: self.MAX_QUERY_LENGTH]

        try:
            with MicrosoftGraphClient.from_request(request) as client:
                users = client.search_users(query, limit=self.RESULT_LIMIT)
        except EntraAuthenticationError:
            return JsonResponse({"error": "authentication_required"}, status=401)
        except EntraRequestError as error:
            sentry_sdk.capture_exception(error)
            return JsonResponse({"error": "search_failed"}, status=502)

        results = [self._serialise(user) for user in users]
        return JsonResponse({"results": results})

    def _serialise(self, user: dict) -> dict:
        return {
            "id": user.get("id"),
            "display_name": user.get("displayName", ""),
            "email": (user.get("mail") or "").strip().lower(),
        }


class ProjectListView(ListView):
    template_name = "projects/list.html"
    context_object_name = "user_projects"
    model = Project

    def get_queryset(self):
        """
        set PK to whatever user you've created in db.
        Code will be deleted once user auth is implemented
        """
        return self.request.user.projects.distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        clear_project_create_session(self.request)
        context["success_message"] = self.request.session.pop("success_message", None)
        return context


class ProjectDetailView(ProjectLayoutContextMixin, UUIDObjectMixin, DetailView):
    template_name = "projects/detail.html"
    context_object_name = "project"
    model = Project
    active_project_section = "overview"

    def get_queryset(self):
        return (
            Project.objects.filter(user_permissions__user=self.request.user)
            .select_related("business_unit", "created_by")
            .prefetch_related("users", "user_permissions__user")
            .distinct()
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["error_message"] = self.request.session.pop("error_message", None)
        return context


class ProjectCreateView(FormView):
    template_name = "projects/create.html"
    form_class = ProjectCreateForm

    def get_initial(self):
        project_data = self.request.session.get(PROJECT_CREATE_SESSION_KEY, {})
        return {
            "name": project_data.get("name", ""),
            "description": project_data.get("description", ""),
            "business_unit": project_data.get("business_unit_id"),
        }

    def form_valid(self, form):
        cleaned = form.cleaned_data
        self.request.session[PROJECT_CREATE_SESSION_KEY] = {
            "name": cleaned["name"],
            "description": cleaned["description"],
            "business_unit_id": cleaned["business_unit"].id,
        }
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse("projects:project_create_add_users")


class ProjectUserSelectionFormView(ProjectUserSelectionSessionMixin, FormView):
    template_name = "projects/user_add.html"

    def get_success_url(self):
        raise NotImplementedError

    def get_initial(self):
        return [
            {
                "oid": member["oid"],
                "email": member.get("email", ""),
                "display_name": member.get("display_name", ""),
            }
            for member in self.get_selected_members()
        ]

    def get_form(self, form_class=None):
        data = self.request.POST if self.request.method == "POST" else None
        initial = self.get_initial() if self.request.method == "GET" else None

        return build_project_add_member_formset(
            project=self.get_project(),
            data=data,
            initial=initial,
            extra=0 if initial else 1,
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["formset"] = context["form"]
        context["project"] = self.get_project()
        context["error_message"] = self.request.session.pop("error_message", None)
        return context

    def form_valid(self, form):
        self.set_selected_members(form.selected_members)
        return redirect(self.get_success_url())


class ProjectCreateAddUsersView(ProjectUserSelectionFormView):
    template_name = "projects/create_user_add.html"

    def get_user_bucket_key(self):
        return USER_BUCKET_SESSION_KEY

    def get_success_url(self):
        return reverse("projects:project_create_confirm")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["project"] = self.request.session.get(PROJECT_CREATE_SESSION_KEY, {})
        context.setdefault("decision_form", self.get_decision_form())
        return context

    def get_decision_form(self):
        data = self.request.POST if self.request.method == "POST" else None
        initial = None
        if self.request.method == "GET" and self.get_selected_members():
            initial = {"add_user": "yes"}
        return ProjectCreateAddUsersDecisionForm(data=data, initial=initial)

    def get_unbound_formset(self):
        initial = None
        extra = 1
        selected_members = self.get_selected_members()
        if selected_members:
            initial = [
                {
                    "oid": member["oid"],
                    "email": member.get("email", ""),
                    "display_name": member.get("display_name", ""),
                }
                for member in selected_members
            ]
            extra = 0

        return build_project_add_member_formset(
            project=self.get_project(),
            data=None,
            initial=initial,
            extra=extra,
        )

    def form_invalid(self, form):
        return self.render_to_response(
            self.get_context_data(form=form, decision_form=self.get_decision_form())
        )

    def post(self, request, *args, **kwargs):
        decision_form = self.get_decision_form()
        if not decision_form.is_valid():
            return self.render_to_response(
                self.get_context_data(
                    form=self.get_unbound_formset(),
                    decision_form=decision_form,
                )
            )

        if decision_form.cleaned_data["add_user"] == "no":
            self.clear_selected_members()
            return redirect("projects:project_create_confirm")

        return super().post(request, *args, **kwargs)


class ProjectCreateConfirmView(
    ProjectMembershipNotificationMixin,
    ProjectUserSelectionSessionMixin,
    View,
):
    template_name = "projects/create_confirm.html"

    def get_user_bucket_key(self):
        return USER_BUCKET_SESSION_KEY

    def get_selected_users(self):
        return self.get_selected_members()

    def validate_project_create_session(self, session_data):

        if not session_data:
            # If no data, form will be unbound and invalid
            return False

        form = ProjectCreateForm(
            data={
                "name": session_data.get("name", ""),
                "description": session_data.get("description", ""),
                "business_unit": session_data.get("business_unit_id"),
            }
        )

        return form.is_valid()

    def get(self, request, *args, **kwargs):
        project_data = self.request.session.get(PROJECT_CREATE_SESSION_KEY, {})
        is_valid = self.validate_project_create_session(project_data)
        if not is_valid:
            return redirect("projects:project_create")

        business_unit_id = project_data.get("business_unit_id") if project_data else None
        business_unit = get_object_or_404(BusinessUnit, pk=business_unit_id)
        selected_users = list(self.get_selected_users())

        context = {
            "project": project_data,
            "business_unit": business_unit,
            "selected_users": selected_users,
        }
        return render(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        project_data = self.request.session.get(PROJECT_CREATE_SESSION_KEY)
        is_valid = self.validate_project_create_session(project_data)
        if not is_valid:
            return redirect("projects:project_create")

        try:
            with ProjectService.from_request(request) as service:
                project, members = service.create_project(
                    name=project_data["name"],
                    description=project_data["description"],
                    business_unit_id=project_data["business_unit_id"],
                    created_by=request.user,
                    selected_members=self.get_selected_members(),
                )
        except EntraDirectoryError as error:
            sentry_sdk.capture_exception(error)
            request.session["error_message"] = {
                "heading": "There was a problem adding one or more members",
                "message": "Please try again.",
            }
            return redirect("projects:project_create_add_users")

        self.send_member_added_notifications(
            project=project, members=members, added_by=request.user
        )

        clear_project_create_session(self.request)
        request.session["success_message"] = {
            "heading": "Project created",
            "message": "You can now generate keys for the AI Gateway API",
        }

        return redirect("projects:project_detail", uuid=project.uuid)


class ProjectUsersDetailView(ProjectLayoutContextMixin, UUIDObjectMixin, DetailView):
    template_name = "projects/user_list.html"
    context_object_name = "project"
    model = Project
    active_project_section = "members"

    def get_queryset(self):
        return (
            Project.objects.filter(user_permissions__user=self.request.user)
            .prefetch_related(
                Prefetch(
                    "user_permissions",
                    queryset=ProjectUserPermissions.objects.select_related("user"),
                )
            )
            .distinct()
        )

    def get_context_data(self, **kwargs):
        self.request.session.pop(ADD_USER_SESSION_KEY, None)
        return super().get_context_data(**kwargs)


class ProjectDeleteView(UUIDObjectMixin, DeleteView):
    """
    Will need additional checks for user permissions to ensure
    the user has access to delete the project.
    """

    template_name = "projects/delete_confirm.html"
    context_object_name = "project"
    model = Project
    success_url = reverse_lazy("projects:projects_list")

    def get_queryset(self):
        return Project.objects.filter(
            user_permissions__user=self.request.user,
            user_permissions__role="admin",
        ).distinct()

    def form_valid(self, form):
        project = self.object

        key_values = list(project.ai_gateway_keys.values_list("litellm_secret", flat=True))
        try:
            team_id = project.ai_gateway_team.litellm_team_id
        except Team.DoesNotExist:
            team_id = None

        try:
            if key_values or team_id:
                with KeyService.from_settings() as service:
                    if key_values:
                        service.bulk_delete_keys(key_values)
                    if team_id:
                        service.delete_team(team_id)

            response = super().form_valid(form)
        except AIGatewayError as error:
            sentry_sdk.capture_exception(error)
            self.request.session["error_message"] = {
                "heading": "Could not delete project. Please try again later.",
            }
            return redirect("projects:project_detail", uuid=project.uuid)

        self.request.session["success_message"] = {"heading": "Project deleted"}
        return response


class ProjectAddUsersView(ExistingProjectMixin, ProjectUserSelectionFormView):
    template_name = "projects/user_add.html"

    def get_success_url(self):
        return reverse(
            "projects:project_users_add_confirm",
            kwargs={"uuid": self.get_project().uuid},
        )


class ProjectAddUsersConfirmView(
    ProjectMembershipNotificationMixin,
    ExistingProjectMixin,
    ProjectUserSelectionSessionMixin,
    View,
):
    template_name = "projects/user_add_confirm.html"

    def get_selected_users(self):
        return self.get_selected_members()

    def get(self, request, *args, **kwargs):
        project = self.get_project()
        selected_users = list(self.get_selected_users())
        if not selected_users:
            return redirect("projects:project_users_add", uuid=project.uuid)

        context = {"project": project, "selected_users": selected_users}
        return render(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        project = self.get_project()
        selections = self.get_selected_members()

        if not selections:
            return redirect("projects:project_users_add", uuid=project.uuid)

        try:
            with ProjectService.from_request(request) as service:
                members_to_add = service.add_members(
                    project=project,
                    selections=selections,
                    added_by=request.user,
                )
        except EntraDirectoryError as error:
            sentry_sdk.capture_exception(error)
            request.session["error_message"] = {
                "heading": "There was a problem adding one or more members",
                "message": "Please try again.",
            }
            return redirect("projects:project_users_add", uuid=project.uuid)

        self.send_member_added_notifications(
            project=project, members=members_to_add, added_by=request.user
        )

        self.clear_selected_members()
        request.session["success_message"] = {
            "heading": "Project member added",
        }

        return redirect("projects:project_users", uuid=project.uuid)


class ProjectRemoveUserView(ProjectMembershipNotificationMixin, DeleteView):
    """
    Will need additional checks for user permissions to ensure
    the user can remove users from the project.
    """

    template_name = "projects/user_remove_confirm.html"
    context_object_name = "membership"
    model = ProjectUserPermissions

    def get_object(self, queryset=None):
        return get_object_or_404(
            ProjectUserPermissions.objects.select_related("project", "user")
            .filter(project__user_permissions__user=self.request.user)
            .distinct(),
            project__uuid=self.kwargs["uuid"],
            user_id=self.kwargs["user_id"],
        )

    def get_success_url(self):
        if self.object.user == self.request.user:
            return reverse("projects:projects_list")

        return reverse("projects:project_users", kwargs={"uuid": self.kwargs["uuid"]})

    def form_valid(self, form):
        membership = self.get_object()
        user_name = membership.user.full_name
        response = super().form_valid(form)
        self.send_member_removed_notification(
            project=membership.project,
            member=membership.user,
            removed_by=self.request.user,
        )
        self.request.session["success_message"] = {
            "heading": f"You have removed {user_name} from this project",
        }
        return response
