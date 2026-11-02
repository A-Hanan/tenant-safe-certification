import uuid

from django.conf import settings
from django.db import models

from accounts.models import User
from institutions.models import Institution, Role


class Status(models.TextChoices):
    DRAFT = "draft", "Draft"
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


class Action(models.TextChoices):
    CREATE = "create", "Create"
    SUBMIT = "submit", "Submit"
    APPROVE = "approve", "Approve"
    REJECT = "reject", "Reject"


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


class ApprovalAuditEvent(models.Model):
    """Model-level immutability only; QuerySet writes and raw SQL bypass it."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    institution = models.ForeignKey(
        Institution, on_delete=models.PROTECT, related_name="approval_audit_events"
    )
    request = models.ForeignKey(
        ApprovalRequest, on_delete=models.PROTECT, related_name="audit_events"
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="approval_audit_events",
    )
    actor_kind = models.CharField(max_length=5, choices=User.Kind.choices)
    actor_role = models.CharField(max_length=9, choices=Role.choices)
    action = models.CharField(max_length=7, choices=Action.choices)
    # Creation has no prior state.
    from_status = models.CharField(max_length=8, choices=Status.choices, blank=True)
    to_status = models.CharField(max_length=8, choices=Status.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(
        self, *, force_insert=False, force_update=False, using=None, update_fields=None
    ):
        if not self._state.adding or force_update or update_fields is not None:
            raise ValueError("Audit events cannot be updated.")
        # A new instance with an existing ID must never overwrite that row.
        return super().save(force_insert=True, using=using)

    def delete(self, using=None, keep_parents=False):
        raise ValueError("Audit events cannot be deleted.")
