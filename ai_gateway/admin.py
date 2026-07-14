from django.contrib import admin

from ai_gateway.models import Key, Team


class AIGatewayTeamAdmin(admin.ModelAdmin):
    list_display = ("project", "litellm_team_id", "created")


class KeyAdmin(admin.ModelAdmin):
    list_display = ("name", "project", "masked_key", "created_by", "created")
    exclude = ("litellm_secret",)


admin.site.register(Team, AIGatewayTeamAdmin)
admin.site.register(Key, KeyAdmin)
