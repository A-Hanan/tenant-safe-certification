import pytest

from approvals.models import Action
from approvals.services import create_request, transition_request
from institutions.models import Role
from tests.factories import MembershipFactory

pytestmark = pytest.mark.django_db


def test_create_request_writes_draft_and_creation_event():
    membership = MembershipFactory(role=Role.SUBMITTER)

    request = create_request(
        actor=membership.user,
        institution=membership.institution,
        title="Demo Tuition Request",
        student_reference="DEMO-STUDENT-001",
        amount_cents=250000,
        currency="USD",
    )

    request.refresh_from_db()
    assert request.institution_id == membership.institution_id
    assert request.created_by_id == membership.user_id
    assert request.status == "draft"
    assert request.title == "Demo Tuition Request"
    assert request.student_reference == "DEMO-STUDENT-001"
    assert request.amount_cents == 250000
    assert request.currency == "USD"

    event = request.audit_events.get()
    assert event.institution_id == membership.institution_id
    assert event.actor_id == membership.user_id
    assert event.actor_kind == "human"
    assert event.actor_role == "submitter"
    assert event.action == Action.CREATE
    assert event.from_status == ""
    assert event.to_status == "draft"
    assert event.created_at is not None


@pytest.mark.parametrize(
    ("action", "expected_status"),
    [(Action.APPROVE, "approved"), (Action.REJECT, "rejected")],
)
def test_submit_then_review_writes_each_audit_event(action, expected_status):
    submitter = MembershipFactory(role=Role.SUBMITTER)
    approver = MembershipFactory(institution=submitter.institution, role=Role.APPROVER)
    request = create_request(
        actor=submitter.user,
        institution=submitter.institution,
        title="Demo Review Request",
        student_reference="DEMO-STUDENT-002",
        amount_cents=250000,
        currency="USD",
    )

    submitted = transition_request(
        actor=submitter.user,
        institution=submitter.institution,
        request_id=request.pk,
        action=Action.SUBMIT,
    )

    assert submitted.pk == request.pk
    assert submitted.status == "pending"
    request.refresh_from_db()
    assert request.status == "pending"
    assert request.audit_events.count() == 2

    reviewed = transition_request(
        actor=approver.user,
        institution=submitter.institution,
        request_id=request.pk,
        action=action,
    )

    assert reviewed.pk == request.pk
    assert reviewed.status == expected_status
    request.refresh_from_db()
    assert request.status == expected_status
    assert request.created_by_id == submitter.user_id
    assert list(
        request.audit_events.order_by("created_at", "id").values_list(
            "institution_id",
            "actor_id",
            "actor_kind",
            "actor_role",
            "action",
            "from_status",
            "to_status",
        )
    ) == [
        (
            submitter.institution_id,
            submitter.user_id,
            "human",
            "submitter",
            Action.CREATE,
            "",
            "draft",
        ),
        (
            submitter.institution_id,
            submitter.user_id,
            "human",
            "submitter",
            Action.SUBMIT,
            "draft",
            "pending",
        ),
        (
            submitter.institution_id,
            approver.user_id,
            "human",
            "approver",
            action,
            "pending",
            expected_status,
        ),
    ]
