import sentry_sdk
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Case, F, IntegerField, Prefetch, Value, When
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.functional import cached_property
from django.views.generic.base import TemplateView, View
from django.views.generic.detail import DetailView
from django.views.generic.edit import DeleteView, FormView
from django.views.generic.list import ListView

from ai_gateway.exceptions import AIGatewayError
from ai_gateway.models import Team
from ai_gateway.services import KeyService
from projects.forms import (
    ProjectCreateAddUsersDecisionForm,
    ProjectCreateForm,
    ProjectMemberForm,
    ProjectMemberPermissionsForm,
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
    ProjectAccessMixin,
    ProjectLayoutContextMixin,
    ProjectMembershipNotificationMixin,
    ProjectPermissionRequiredMixin,
    ProjectUserSelectionSessionMixin,
    UUIDObjectMixin,
)
from projects.models import BusinessUnit, Project, ProjectMembership, ProjectPermission
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

        # Members are identified by email throughout the flow, so drop any
        # directory results that have none.
        results = [serialised for user in users if (serialised := self._serialise(user))["email"]]
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


class ProjectDetailView(
    ProjectAccessMixin, ProjectLayoutContextMixin, UUIDObjectMixin, DetailView
):
    template_name = "projects/detail.html"
    context_object_name = "project"
    model = Project
    active_project_section = "overview"

    def get_queryset(self):
        return self.get_accessible_projects(
            Project.objects.select_related("business_unit", "created_by").prefetch_related(
                "users", "memberships__user"
            )
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


class ProjectCreateAddUsersView(ProjectUserSelectionSessionMixin, FormView):
    """The yes/no decision on whether to add members during project creation."""

    template_name = "projects/create_member_add.html"
    form_class = ProjectCreateAddUsersDecisionForm

    def get_user_bucket_key(self):
        return USER_BUCKET_SESSION_KEY

    def get_initial(self):
        return {"add_user": "yes"} if self.get_selected_members() else {}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["project"] = self.request.session.get(PROJECT_CREATE_SESSION_KEY, {})
        context["error_message"] = self.request.session.pop("error_message", None)
        return context

    def form_valid(self, form):
        if form.cleaned_data["add_user"] == "no":
            self.clear_selected_members()
            return redirect("projects:project_create_confirm")
        return redirect("projects:project_create_add_member")


class ProjectMemberFormBaseView(ProjectUserSelectionSessionMixin, FormView):
    """Search for a user and choose their permissions, one member at a time.

    Shared by the project-creation and existing-project add-member flows;
    subclasses only differ in bucket key, success url and cancel target.
    """

    template_name = "projects/member_add.html"
    form_class = ProjectMemberForm

    def get_editing_oid(self):
        return self.request.GET.get("edit")

    def get_cancel_url(self):
        raise NotImplementedError

    def get_review_url(self):
        raise NotImplementedError

    def get_entry_url(self):
        raise NotImplementedError

    def get_back_url(self):
        if self.get_editing_oid() or self.get_selected_members():
            return self.get_review_url()
        return self.get_entry_url()

    def get_initial(self):
        editing_oid = self.get_editing_oid()
        member = self.get_selected_member(editing_oid) if editing_oid else None
        if not member:
            return {}
        return {
            "oid": member["oid"],
            "email": member.get("email", ""),
            "display_name": member.get("display_name", ""),
            "permissions": member.get("permissions", []),
        }

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["project"] = self.get_project()
        kwargs["existing_oids"] = self.get_member_oids()
        kwargs["editing_oid"] = self.get_editing_oid()
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["project"] = self.get_project()
        context["cancel_url"] = self.get_cancel_url()
        context["back_url"] = self.get_back_url()
        context["error_message"] = self.request.session.pop("error_message", None)
        return context

    def form_valid(self, form):
        member = {
            "oid": form.cleaned_data["oid"],
            "email": form.cleaned_data.get("email", ""),
            "display_name": form.cleaned_data.get("display_name", ""),
            "permissions": form.cleaned_data.get("permissions", []),
        }
        self.upsert_selected_member(member, editing_oid=self.get_editing_oid())
        return redirect(self.get_success_url())


class ProjectCreateAddMemberView(ProjectMemberFormBaseView):
    def get_user_bucket_key(self):
        return USER_BUCKET_SESSION_KEY

    def get_success_url(self):
        return reverse("projects:project_create_review_members")

    def get_review_url(self):
        return reverse("projects:project_create_review_members")

    def get_entry_url(self):
        return reverse("projects:project_create_add_users")

    def get_cancel_url(self):
        return reverse("projects:projects_list")


class ProjectReviewMembersBaseView(ProjectUserSelectionSessionMixin, View):
    """Lists members added so far, with add-another/change/remove actions."""

    template_name = "projects/create_review_members.html"

    def get_context_data(self):
        return {
            "project": self.get_project(),
            "selected_members": self.get_selected_members_with_permission_labels(),
        }

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, self.get_context_data())

    def post(self, request, *args, **kwargs):
        remove_oid = request.POST.get("remove_oid")
        if remove_oid:
            self.remove_selected_member(remove_oid)
        return redirect(request.path)


class ProjectCreateReviewMembersView(ProjectReviewMembersBaseView):
    template_name = "projects/create_review_members.html"

    def get_user_bucket_key(self):
        return USER_BUCKET_SESSION_KEY

    def get_context_data(self):
        context = super().get_context_data()
        context["add_member_url"] = reverse("projects:project_create_add_member")
        context["continue_url"] = reverse("projects:project_create_confirm")
        context["cancel_url"] = reverse("projects:projects_list")
        return context


class ProjectCreateConfirmView(
    ProjectMembershipNotificationMixin,
    ProjectUserSelectionSessionMixin,
    View,
):
    template_name = "projects/create_confirm.html"

    def get_user_bucket_key(self):
        return USER_BUCKET_SESSION_KEY

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

        context = {
            "project": project_data,
            "business_unit": business_unit,
            "selected_members": self.get_selected_members_with_permission_labels(),
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


class ProjectUsersListView(ExistingProjectMixin, ProjectLayoutContextMixin, TemplateView):
    template_name = "projects/member_list.html"
    active_project_section = "members"

    def get_accessible_projects(self):
        queryset = super().get_accessible_projects()
        return queryset.prefetch_related(
            Prefetch(
                "memberships",
                queryset=ProjectMembership.objects.select_related("user")
                .prefetch_related("permissions__permission")
                .annotate(
                    owner_order=Case(
                        When(user_id=F("project__owner_id"), then=Value(0)),
                        default=Value(1),
                        output_field=IntegerField(),
                    )
                )
                .order_by("owner_order", "user__email"),
            )
        )

    def get_context_data(self, **kwargs):
        self.request.session.pop(ADD_USER_SESSION_KEY, None)
        return super().get_context_data(**kwargs)


class ProjectDeleteView(ProjectAccessMixin, UUIDObjectMixin, DeleteView):
    """
    View to delete a project. There is no specific permission for deleting a project, it is only
    accessible to project owners and superusers.
    """

    template_name = "projects/delete_confirm.html"
    context_object_name = "project"
    model = Project
    success_url = reverse_lazy("projects:projects_list")

    def get_queryset(self):
        queryset = self.get_accessible_projects()
        if self.request.user.is_superuser:
            return queryset
        return queryset.filter(owner=self.request.user)

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


class ProjectAddUsersView(
    ProjectPermissionRequiredMixin, ExistingProjectMixin, ProjectMemberFormBaseView
):
    permission_required = ProjectPermission.MANAGE_MEMBERS.permission_name
    template_name = "projects/member_add.html"

    def get_success_url(self):
        return reverse(
            "projects:project_users_add_review",
            kwargs={"uuid": self.get_project().uuid},
        )

    def get_review_url(self):
        return reverse(
            "projects:project_users_add_review", kwargs={"uuid": self.get_project().uuid}
        )

    def get_entry_url(self):
        return reverse("projects:project_users", kwargs={"uuid": self.get_project().uuid})

    def get_cancel_url(self):
        return reverse("projects:project_users", kwargs={"uuid": self.get_project().uuid})


class ProjectAddUsersReviewView(
    ProjectPermissionRequiredMixin,
    ProjectMembershipNotificationMixin,
    ExistingProjectMixin,
    ProjectUserSelectionSessionMixin,
    View,
):
    permission_required = ProjectPermission.MANAGE_MEMBERS.permission_name
    template_name = "projects/member_add_review.html"

    def get_selected_users(self):
        return self.get_selected_members()

    def get(self, request, *args, **kwargs):
        project = self.get_project()
        if not self.get_selected_members():
            return redirect("projects:project_users_add", uuid=project.uuid)

        context = {
            "project": project,
            "selected_members": self.get_selected_members_with_permission_labels(),
        }
        return render(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        project = self.get_project()

        remove_oid = request.POST.get("remove_oid")
        if remove_oid:
            self.remove_selected_member(remove_oid)
            return redirect("projects:project_users_add_review", uuid=project.uuid)

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


class ProjectMemberEditView(
    ProjectPermissionRequiredMixin,
    ExistingProjectMixin,
    FormView,
):
    permission_required = ProjectPermission.MANAGE_MEMBERS.permission_name
    template_name = "projects/member_edit.html"
    form_class = ProjectMemberPermissionsForm

    @cached_property
    def membership(self):
        return get_object_or_404(
            self.project.memberships.select_related("user", "project"),
            pk=self.kwargs["pk"],
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["membership"] = self.membership
        context["success_message"] = self.request.session.pop("success_message", None)
        return context

    def get_initial(self):
        initial = super().get_initial()
        initial["permissions"] = list(
            self.membership.permissions.values_list("permission__codename", flat=True)
        )
        return initial

    def form_valid(self, form):
        permission_codenames = form.cleaned_data["permissions"]
        with ProjectService.from_request(self.request) as service:
            service.update_member_permissions(
                membership=self.membership,
                permission_codenames=permission_codenames,
                updated_by=self.request.user,
            )

        self.request.session["success_message"] = {
            "heading": "Permissions updated",
        }
        return super().form_valid(form)

    def get_success_url(self):
        return reverse(
            "projects:project_member_edit",
            kwargs={"uuid": self.project.uuid, "pk": self.membership.pk},
        )


class ProjectRemoveUserView(
    ProjectPermissionRequiredMixin,
    ExistingProjectMixin,
    ProjectMembershipNotificationMixin,
    DeleteView,
):
    permission_required = ProjectPermission.MANAGE_MEMBERS.permission_name
    template_name = "projects/member_remove_confirm.html"
    context_object_name = "membership"
    model = ProjectMembership

    def get_object(self, queryset=None):
        membership_qs = (
            ProjectMembership.objects.filter(project__in=self.get_accessible_projects())
            .exclude(project__owner=self.kwargs["user_id"])
            .select_related("project", "user")
        )
        return get_object_or_404(
            membership_qs,
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
