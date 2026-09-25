from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from ai_gateway.admin import AIGatewayTeamInline
from projects.models import BusinessUnit, Project, ProjectMembership, ProjectMembershipPermission


class BusinessUnitAdmin(admin.ModelAdmin):
    list_display = ("name", "code")
    search_fields = ("name", "code")
    readonly_fields = ("created", "modified")


class ProjectMembershipInline(admin.TabularInline):
    model = ProjectMembership
    extra = 0
    autocomplete_fields = ("user",)
    fields = (
        "user",
        "permission_list",
    )
    readonly_fields = ("permission_list",)
    show_change_link = True

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("permissions__permission")

    @admin.display(description="Permissions")
    def permission_list(self, obj):
        if not obj.pk:
            return ""

        return ", ".join(assignment.permission.name for assignment in obj.permissions.all())


class ProjectMembershipPermissionInline(admin.TabularInline):
    model = ProjectMembershipPermission
    extra = 0

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .prefetch_related("permission")
            .select_related("granted_by", "membership__project", "membership__user")
        )


class ProjectMembershipAdmin(SimpleHistoryAdmin):
    list_display = ("project", "user", "created")
    list_filter = ("project",)
    search_fields = ("project__name", "user__email")
    readonly_fields = ("project", "user", "created", "modified")
    inlines = (ProjectMembershipPermissionInline,)
    list_select_related = ("project", "user")


class ProjectAdmin(SimpleHistoryAdmin):
    list_display = ("name", "business_unit", "owner", "created_by", "created")
    list_filter = ("business_unit",)
    search_fields = ("name",)
    readonly_fields = ("uuid", "created_by", "created", "modified")
    inlines = (ProjectMembershipInline, AIGatewayTeamInline)
    list_select_related = ("business_unit", "created_by", "owner")


HISTORY_TYPE_LABELS = {"+": "Added", "~": "Changed", "-": "Removed"}


class ProjectMembershipAuditAdmin(admin.ModelAdmin):
    """Read-only audit log — includes records for removed users."""

    verbose_name = "Project membership audit log"
    list_display = (
        "project",
        "project_id",
        "user",
        "user_id",
        "history_type_display",
        "history_date",
        "history_user",
        "history_user_id",
    )
    list_filter = ("history_type",)
    search_fields = ("project_id", "project__name", "user__email")
    ordering = ("-history_date",)
    readonly_fields = ("project_id", "user_id", "history_user_id")

    @admin.display(description="Action")
    def history_type_display(self, obj):
        return HISTORY_TYPE_LABELS.get(obj.history_type, obj.history_type)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class ProjectMembershipPermissionAuditAdmin(admin.ModelAdmin):
    list_display = (
        "membership",
        "membership_id",
        "permission",
        "granted_by",
        "granted_by_id",
        "history_type_display",
        "history_date",
        "history_user",
        "history_user_id",
    )
    list_filter = ("history_type", "permission")
    search_fields = (
        "membership_id",
        "membership__project__name",
        "membership__user__email",
        "permission__codename",
    )
    ordering = ("-history_date",)
    list_select_related = ("membership", "permission", "granted_by", "history_user")
    readonly_fields = ("membership_id", "granted_by_id", "history_user_id")

    @admin.display(description="Action")
    def history_type_display(self, obj):
        return HISTORY_TYPE_LABELS.get(
            obj.history_type,
            obj.history_type,
        )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(BusinessUnit, BusinessUnitAdmin)
admin.site.register(Project, ProjectAdmin)
admin.site.register(ProjectMembership, ProjectMembershipAdmin)
admin.site.register(ProjectMembership.history.model, ProjectMembershipAuditAdmin)
admin.site.register(
    ProjectMembershipPermission.history.model, ProjectMembershipPermissionAuditAdmin
)
