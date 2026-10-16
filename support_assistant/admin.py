from django.contrib import admin

from support_assistant.models import Feedback, GuideChunk, Interaction


@admin.register(GuideChunk)
class GuideChunkAdmin(admin.ModelAdmin):
    list_display = ["page_title", "heading", "source_path", "position", "updated_at"]
    search_fields = ["page_title", "heading", "content", "source_path"]
    readonly_fields = [field.name for field in GuideChunk._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class FeedbackInline(admin.StackedInline):
    model = Feedback
    readonly_fields = ["helpful", "comment", "created_at", "updated_at"]
    can_delete = False
    extra = 0


@admin.register(Interaction)
class InteractionAdmin(admin.ModelAdmin):
    list_display = ["created_at", "outcome", "question", "feedback__helpful", "latency_ms"]
    list_filter = ["outcome", "feedback__helpful", "created_at"]
    search_fields = ["question", "answer"]
    readonly_fields = [field.name for field in Interaction._meta.fields]
    inlines = [FeedbackInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
