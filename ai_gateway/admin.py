import logging

from django import forms
from django.contrib import admin, messages
from simple_history.admin import SimpleHistoryAdmin

from ai_gateway.models import Key, Team
from ai_gateway.services import AccessGroupService, KeyService

logger = logging.getLogger(__name__)


class AIGatewayTeamAdminForm(forms.ModelForm):
    access_groups = forms.MultipleChoiceField(
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Access groups",
        help_text="Access groups grant this team's keys access to additional models.",
    )

    class Meta:
        model = Team
        fields = []


class AIGatewayTeamAdmin(SimpleHistoryAdmin):
    form = AIGatewayTeamAdminForm
    list_display = ("project", "litellm_team_id", "created")
    readonly_fields = ("project", "litellm_team_id", "created", "modified")
    fieldsets = (
        (None, {"fields": ("project", "litellm_team_id", "created", "modified")}),
        ("Access groups", {"fields": ("access_groups",)}),
    )

    def get_form(self, request, obj=None, **kwargs):
        """Return a form pre-populated with the team's access groups from the gateway.

        ``get_form`` must return a form class, but the access-group choices and
        the team's current selection are only known at request time. A per-request
        subclass is returned so those runtime values are baked into every instance
        the admin builds.
        """
        base_form_class = super().get_form(request, obj, **kwargs)
        if obj is None:
            return base_form_class

        with AccessGroupService.from_settings() as service:
            choices = [
                (group["access_group_id"], group["access_group_name"])
                for group in service.list_access_groups()
            ]
            initial = service.get_team_access_group_ids(obj)

        logger.info(
            "AI Gateway access groups for team %s viewed by %s: %s",
            obj.litellm_team_id,
            request.user,
            initial,
        )

        class AIGatewayTeamForm(base_form_class):
            def __init__(self, *args, **form_kwargs):
                super().__init__(*args, **form_kwargs)
                self.fields["access_groups"].choices = choices
                self.initial["access_groups"] = initial

        return AIGatewayTeamForm

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change:
            return
        selected = form.cleaned_data.get("access_groups", [])
        previous = form.initial.get("access_groups", [])
        with AccessGroupService.from_settings() as service:
            service.set_team_access_groups(obj, selected)

        logger.info(
            "AI Gateway access groups for team %s updated by %s: %s",
            obj.litellm_team_id,
            request.user,
            selected,
        )

        if set(previous) - set(selected):
            self._reconcile_team_keys(request, obj)

    def _reconcile_team_keys(self, request, team):
        """Prune models newly restricted from the team's keys, reporting outcomes."""
        with KeyService.from_settings() as service:
            updated, failed = service.prune_team_keys_to_allowed_models(team)

        if updated:
            messages.info(
                request,
                f"Removed newly restricted models from {len(updated)} key(s).",
            )
        if failed:
            messages.error(
                request,
                f"Could not update {len(failed)} key(s): {', '.join(failed)}.",
            )


class KeyAdmin(SimpleHistoryAdmin):
    list_display = ("name", "project", "masked_key", "created_by", "created")
    exclude = ("litellm_secret",)
    readonly_fields = (
        "project",
        "litellm_alias",
        "litellm_token",
        "masked_key",
        "created_by",
        "created",
        "modified",
    )


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
