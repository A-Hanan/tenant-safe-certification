import pytest
from django.contrib import admin
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import RequestFactory
from django.urls import reverse

from accounts.models import User
from approvals.models import Action, ApprovalAuditEvent, Status
from institutions.models import Role
from tests.factories import ApprovalRequestFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def audit_event():
    approval = ApprovalRequestFactory()
    return ApprovalAuditEvent.objects.create(
        institution=approval.institution,
        request=approval,
        actor=approval.created_by,
        actor_kind=User.Kind.HUMAN,
        actor_role=Role.SUBMITTER,
        action=Action.CREATE,
        from_status="",
        to_status=Status.DRAFT,
    )


def test_audit_event_can_be_created(audit_event):
    audit_event.refresh_from_db()

    assert audit_event.action == Action.CREATE
    assert audit_event.from_status == ""
    assert audit_event.to_status == "draft"
    assert audit_event.actor_kind == "human"
    assert audit_event.actor_role == "submitter"
    assert audit_event.created_at is not None


@pytest.mark.parametrize(
    "save_kwargs", [{}, {"update_fields": ["to_status"]}, {"force_update": True}]
)
def test_audit_event_cannot_be_updated(audit_event, save_kwargs):
    event = ApprovalAuditEvent.objects.get(pk=audit_event.pk)
    event.to_status = Status.APPROVED

    with pytest.raises(ValueError, match="Audit events cannot be updated"):
        event.save(**save_kwargs)

    event.refresh_from_db()
    assert event.to_status == "draft"


def test_new_instance_cannot_overwrite_existing_audit_event(audit_event):
    replacement = ApprovalAuditEvent(
        id=audit_event.pk,
        institution=audit_event.institution,
        request=audit_event.request,
        actor=audit_event.actor,
        actor_kind=User.Kind.HUMAN,
        actor_role=Role.APPROVER,
        action=Action.APPROVE,
        from_status=Status.PENDING,
        to_status=Status.APPROVED,
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        replacement.save()

    audit_event.refresh_from_db()
    assert audit_event.action == Action.CREATE
    assert audit_event.to_status == "draft"


def test_audit_event_cannot_be_deleted(audit_event):
    event_id = audit_event.pk

    with pytest.raises(ValueError, match="Audit events cannot be deleted"):
        audit_event.delete()

    assert ApprovalAuditEvent.objects.filter(pk=event_id).exists()


@pytest.mark.parametrize("relation", ["institution", "request", "actor"])
def test_audit_event_protects_referenced_records(audit_event, relation):
    with pytest.raises(ProtectedError) as exc:
        getattr(audit_event, relation).delete()

    assert audit_event in exc.value.protected_objects
    assert ApprovalAuditEvent.objects.filter(pk=audit_event.pk).exists()


@pytest.fixture
def superuser():
    return UserFactory(is_staff=True, is_superuser=True)


def test_audit_admin_is_read_only_even_for_superuser(audit_event, superuser):
    request = RequestFactory().get("/admin/")
    request.user = superuser
    model_admin = admin.site.get_model_admin(ApprovalAuditEvent)

    assert model_admin.has_view_permission(request, audit_event) is True
    assert model_admin.has_add_permission(request) is False
    assert model_admin.has_change_permission(request) is False
    assert model_admin.has_change_permission(request, audit_event) is False
    assert model_admin.has_delete_permission(request) is False
    assert model_admin.has_delete_permission(request, audit_event) is False
    assert model_admin.get_actions(request) == {}


def test_audit_admin_allows_viewing_events(client, superuser, audit_event):
    client.force_login(superuser)

    listing = client.get(reverse("admin:approvals_approvalauditevent_changelist"))
    detail = client.get(
        reverse("admin:approvals_approvalauditevent_change", args=[audit_event.pk])
    )

    assert listing.status_code == 200
    assert detail.status_code == 200


@pytest.mark.parametrize(
    ("route", "needs_object"),
    [
        ("admin:approvals_approvalauditevent_add", False),
        ("admin:approvals_approvalauditevent_change", True),
        ("admin:approvals_approvalauditevent_delete", True),
    ],
)
def test_audit_admin_rejects_writes(
    client, superuser, audit_event, route, needs_object
):
    client.force_login(superuser)
    url = reverse(route, args=[audit_event.pk] if needs_object else None)

    response = client.post(url, {"to_status": "approved", "post": "yes"})

    assert response.status_code == 403
    assert ApprovalAuditEvent.objects.count() == 1
    audit_event.refresh_from_db()
    assert audit_event.to_status == "draft"
