import uuid

from django.conf import settings
from django.db import models

from institutions.models import Institution


class Status(models.TextChoices):
    DRAFT = "draft", "Draft"
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


class ApprovalRequestQuerySet(models.QuerySet):
    def for_institution(self, institution):
        return self.filter(institution=institution)


class ApprovalRequest(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    institution = models.ForeignKey(
        Institution,
        on_delete=models.PROTECT,
        related_name="approval_requests",
    )
    title = models.CharField(max_length=200)
    student_reference = models.CharField(max_length=64)
    amount_cents = models.BigIntegerField()
    currency = models.CharField(max_length=3)
    status = models.CharField(
        max_length=8, choices=Status.choices, default=Status.DRAFT
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="approval_requests",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ApprovalRequestQuerySet.as_manager()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount_cents__gt=0),
                name="approval_amount_cents_positive",
            ),
        ]
        indexes = [
            models.Index(
                fields=["institution", "status", "created_at"],
                name="approval_tenant_status_idx",
            ),
        ]
