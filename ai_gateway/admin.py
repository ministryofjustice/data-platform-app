from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from ai_gateway.models import Key, Team


class AIGatewayTeamAdmin(SimpleHistoryAdmin):
    list_display = ("project", "litellm_team_id", "created")


class KeyAdmin(SimpleHistoryAdmin):
    list_display = ("name", "project", "masked_key", "created_by", "created")
    exclude = ("litellm_secret",)


HISTORY_TYPE_LABELS = {"+": "Added", "~": "Changed", "-": "Deleted"}


class KeyAuditAdmin(admin.ModelAdmin):
    """Read-only audit log — includes records for deleted keys."""

    list_display = (
        "name",
        "project",
        "masked_key",
        "created_by",
        "history_type_display",
        "history_date",
        "history_user",
    )
    list_filter = ("history_type",)
    search_fields = ("name", "project__name")
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


admin.site.register(Team, AIGatewayTeamAdmin)
admin.site.register(Key, KeyAdmin)
admin.site.register(Key.history.model, KeyAuditAdmin)
