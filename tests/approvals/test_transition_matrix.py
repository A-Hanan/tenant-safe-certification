import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from approvals.models import Action, ApprovalAuditEvent
from institutions.models import Role
from tests.factories import ApprovalRequestFactory, MembershipFactory

pytestmark = pytest.mark.django_db

# Expectations stay independent of the service's transition and role tables.
CASES = [
    ("creator", Action.SUBMIT, "draft", 200, "pending", None),
    ("submitter", Action.SUBMIT, "draft", 403, "draft", "forbidden"),
    ("approver", Action.SUBMIT, "draft", 403, "draft", "forbidden"),
    ("viewer", Action.SUBMIT, "draft", 403, "draft", "forbidden"),
    ("creator", Action.SUBMIT, "pending", 409, "pending", "invalid_transition"),
    ("approver", Action.APPROVE, "pending", 200, "approved", None),
    ("approver", Action.REJECT, "pending", 200, "rejected", None),
    ("submitter", Action.APPROVE, "pending", 403, "pending", "forbidden"),
    ("viewer", Action.APPROVE, "pending", 403, "pending", "forbidden"),
    ("viewer", Action.REJECT, "pending", 403, "pending", "forbidden"),
    ("approver", Action.APPROVE, "draft", 409, "draft", "invalid_transition"),
    ("approver", Action.REJECT, "draft", 409, "draft", "invalid_transition"),
    ("approver", Action.APPROVE, "approved", 409, "approved", "invalid_transition"),
    ("approver", Action.REJECT, "approved", 409, "approved", "invalid_transition"),
    ("approver", Action.APPROVE, "rejected", 409, "rejected", "invalid_transition"),
    ("creator", Action.SUBMIT, "approved", 409, "approved", "invalid_transition"),
    ("creator", Action.SUBMIT, "rejected", 409, "rejected", "invalid_transition"),
]


@pytest.mark.parametrize(
    (
        "actor_name",
        "action",
        "initial_status",
        "expected_http",
        "expected_status",
        "expected_code",
    ),
    CASES,
)
def test_permission_and_state_matrix(
    actor_name, action, initial_status, expected_http, expected_status, expected_code
):
    creator = MembershipFactory(role=Role.SUBMITTER)
    if actor_name == "creator":
        membership = creator
    else:
        membership = MembershipFactory(
            institution=creator.institution,
            role={
                "submitter": Role.SUBMITTER,
                "approver": Role.APPROVER,
                "viewer": Role.VIEWER,
            }[actor_name],
        )

    # Set the starting state directly so setup does not depend on the service.
    approval = ApprovalRequestFactory(
        institution=creator.institution,
        created_by=creator.user,
        status=initial_status,
    )
    original_updated_at = approval.updated_at
    client = APIClient()
    client.force_authenticate(user=membership.user)

    response = client.post(
        reverse(
            f"approval-{action}",
            kwargs={"institution_id": creator.institution_id, "pk": approval.pk},
        )
    )

    assert response.status_code == expected_http
    approval.refresh_from_db()
    assert approval.status == expected_status

    if expected_http != 200:
        assert response.json()["code"] == expected_code
        assert approval.status == initial_status
        assert approval.updated_at == original_updated_at
        assert not ApprovalAuditEvent.objects.exists()
    else:
        assert response.json()["status"] == expected_status
        assert ApprovalAuditEvent.objects.count() == 1
        event = approval.audit_events.get()
        assert event.institution_id == creator.institution_id
        assert event.actor_id == membership.user_id
        assert event.actor_kind == "human"
        assert event.actor_role == membership.role
        assert event.action == action
        assert event.from_status == initial_status
        assert event.to_status == expected_status
