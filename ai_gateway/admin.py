import logging
from collections.abc import Iterable

from django import forms
from django.conf import settings
from django.contrib import admin, messages
from simple_history.admin import SimpleHistoryAdmin

from ai_gateway.models import Key, Team
from ai_gateway.services import KeyService

logger = logging.getLogger(__name__)


class AccessGroupCheckboxSelectMultiple(forms.CheckboxSelectMultiple):
    """Checkbox list that renders selected option values as disabled."""

    def __init__(self, *args, disabled_values: Iterable[str] | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.disabled_values = set(disabled_values or ())

    def create_option(self, name, value, *args, **kwargs):
        option = super().create_option(name, value, *args, **kwargs)
        if str(value) in self.disabled_values:
            option["attrs"]["disabled"] = True
        return option


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


class AIGatewayTeamInline(admin.StackedInline):
    """Read-only link from a project to its AI Gateway team, if one exists."""

    model = Team
    extra = 0
    can_delete = False
    show_change_link = True
    fields = ("litellm_team_id",)
    readonly_fields = ("litellm_team_id",)
    verbose_name = "AI Gateway team"

    def has_add_permission(self, request, obj=None):
        return False


class AIGatewayTeamAdmin(SimpleHistoryAdmin):
    form = AIGatewayTeamAdminForm
    list_display = ("project", "litellm_team_id", "created")
    readonly_fields = ("project", "litellm_team_id", "created", "modified")
    fieldsets = (
        (None, {"fields": ("project", "litellm_team_id", "created", "modified")}),
        ("Access groups", {"fields": ("access_groups",)}),
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

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

        with KeyService.from_settings() as service:
            groups = service.list_access_groups()
            initial = service.get_team_access_group_ids(obj)

        choices = []
        default_access_group_id = None
        for group in groups:
            choices.append((group["access_group_id"], group["access_group_name"]))
            if group["access_group_name"] == settings.DEFAULT_ACCESS_GROUP_NAME:
                default_access_group_id = group["access_group_id"]

        logger.info(
            "AI Gateway access groups for team %s viewed by %s: %s",
            obj.litellm_team_id,
            request.user,
            initial,
        )

        class AIGatewayTeamForm(base_form_class):
            default_group_id = default_access_group_id

            def __init__(self, *args, **form_kwargs):
                super().__init__(*args, **form_kwargs)
                self.initial["access_groups"] = initial
                self.fields["access_groups"].widget = AccessGroupCheckboxSelectMultiple(
                    disabled_values={default_access_group_id} if default_access_group_id else set()
                )
                self.fields["access_groups"].choices = choices

            def clean_access_groups(self):
                # The default group is disabled in the form, so it is never submitted.
                selected = self.cleaned_data["access_groups"]
                if self.default_group_id and self.default_group_id not in selected:
                    selected.append(self.default_group_id)
                return selected

        return AIGatewayTeamForm

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change:
            return

        new_groups = form.cleaned_data.get("access_groups", [])
        initial_groups = form.initial.get("access_groups", [])
        if set(new_groups) == set(initial_groups):
            return

        with KeyService.from_settings() as service:
            updated, failed = service.set_team_model_access(
                obj,
                new_groups,
                changed_by=request.user,
            )

        logger.info(
            "AI Gateway access groups for team %s updated by %s: %s",
            obj.litellm_team_id,
            request.user,
            new_groups,
        )

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
        "models",
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
        "models",
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
