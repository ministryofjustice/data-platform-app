from django.contrib import admin

from projects.models import BusinessUnit, Project, ProjectMember


@admin.register(BusinessUnit)
class BusinessUnitAdmin(admin.ModelAdmin):
    list_display = ("name", "code")
    search_fields = ("name", "code")
    ordering = ("name",)


class ProjectMemberInline(admin.TabularInline):
    model = ProjectMember
    extra = 0


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "business_unit", "created_by", "created")
    search_fields = ("name", "slug", "description")
    list_filter = ("business_unit",)
    inlines = [ProjectMemberInline]
