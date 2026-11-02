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


class ApprovalRequestCreateSerializer(serializers.ModelSerializer):
    currency = serializers.RegexField(regex=r"\A[A-Za-z]{3}\Z")

    class Meta:
        model = ApprovalRequest
        fields = ["title", "student_reference", "amount_cents", "currency"]
        extra_kwargs = {"amount_cents": {"min_value": 1}}

    def validate_currency(self, value):
        return value.upper()
