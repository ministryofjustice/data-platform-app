from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from projects.models import BusinessUnit, Project, ProjectUserPermissions


class BusinessUnitAdmin(admin.ModelAdmin):
    list_display = ("name", "code")
    search_fields = ("name", "code")


class ProjectUserPermissionsInline(admin.TabularInline):
    model = ProjectUserPermissions
    extra = 0
    autocomplete_fields = ("user",)
    fields = ("user", "role")


class ProjectUserPermissionsAdmin(SimpleHistoryAdmin):
    list_display = ("project", "user", "role", "created")
    list_filter = ("project", "role")
    search_fields = ("project__name", "user__email")
    raw_id_fields = ("project", "user")


class ProjectAdmin(SimpleHistoryAdmin):
    list_display = ("name", "business_unit", "created_by", "created")
    list_filter = ("business_unit",)
    search_fields = ("name",)
    readonly_fields = ("uuid", "created", "modified")
    inlines = (ProjectUserPermissionsInline,)
    raw_id_fields = ("created_by",)


HISTORY_TYPE_LABELS = {"+": "Added", "~": "Changed", "-": "Removed"}


class ProjectMembershipAuditAdmin(admin.ModelAdmin):
    """Read-only audit log — includes records for removed users."""

    verbose_name = "Project membership audit log"
    list_display = (
        "project",
        "user",
        "role",
        "history_type_display",
        "history_date",
        "history_user",
    )
    list_filter = ("history_type",)
    search_fields = ("project__name", "user__email")
    ordering = ("-history_date",)

    @admin.display(description="Action")
    def history_type_display(self, obj):
        return HISTORY_TYPE_LABELS.get(obj.history_type, obj.history_type)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(BusinessUnit, BusinessUnitAdmin)
admin.site.register(Project, ProjectAdmin)
admin.site.register(ProjectUserPermissions, ProjectUserPermissionsAdmin)
admin.site.register(ProjectUserPermissions.history.model, ProjectMembershipAuditAdmin)
