from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Admin for the Entra-authenticated user model."""

    ordering = ("email",)
    list_display = ("oid", "username", "email", "is_staff")
    search_fields = ("oid__iexact", "username", "first_name", "last_name", "email")
    fieldsets = (
        (None, {"fields": ("oid", "password")}),
        ("Personal info", {"fields": ("username", "first_name", "last_name", "email")}),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("oid", "password1", "password2"),
            },
        ),
    )
