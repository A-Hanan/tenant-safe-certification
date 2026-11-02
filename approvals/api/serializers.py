from rest_framework import serializers

from approvals.models import ApprovalRequest


class ApprovalRequestReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = ApprovalRequest
        fields = [
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
        ]
        read_only_fields = fields
