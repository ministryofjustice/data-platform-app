# Register your models here.
from django.contrib import admin

from projects.models import BusinessUnit


class BusinessUnitAdmin(admin.ModelAdmin):
    list_display = ("name", "code")


admin.site.register(BusinessUnit, BusinessUnitAdmin)
