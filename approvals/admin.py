from django.contrib import admin

from .models import ApprovalRequest


@admin.register(ApprovalRequest)
class ApprovalRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "institution", "status", "amount_cents", "currency")
    readonly_fields = (
        "id",
        "institution",
        "title",
        "student_reference",
        "amount_cents",
        "currency",
        "status",
        "created_by",
        "created_at",
        "updated_at",
    )
    actions = None

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
