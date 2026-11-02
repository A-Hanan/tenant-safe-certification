from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("Principal", {"fields": ("id", "kind")}),)
    add_fieldsets = UserAdmin.add_fieldsets + (("Principal", {"fields": ("kind",)}),)
    readonly_fields = ("id",)
    list_display = UserAdmin.list_display + ("kind",)
    list_filter = UserAdmin.list_filter + ("kind",)
