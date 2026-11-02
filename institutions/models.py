import uuid

from django.conf import settings
from django.db import models


class Institution(models.Model):
    class Kind(models.TextChoices):
        SCHOOL = "school", "School"
        LENDER = "lender", "Lender"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    kind = models.CharField(max_length=6, choices=Kind.choices)


class Role(models.TextChoices):
    SUBMITTER = "submitter", "Submitter"
    APPROVER = "approver", "Approver"
    VIEWER = "viewer", "Viewer"


class MembershipQuerySet(models.QuerySet):
    def active_for(self, *, user, institution_id):
        return (
            self.select_related("institution")
            .filter(user=user, institution_id=institution_id, is_active=True)
            .first()
        )


class Membership(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="memberships",
    )
    institution = models.ForeignKey(
        Institution,
        on_delete=models.PROTECT,
        related_name="memberships",
    )
    role = models.CharField(max_length=9, choices=Role.choices)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = MembershipQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "institution"],
                name="unique_user_institution_membership",
            ),
        ]
