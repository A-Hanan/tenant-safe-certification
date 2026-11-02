import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import User
from approvals.models import Action, ApprovalAuditEvent, ApprovalRequest, Status
from approvals.services import transition_request
from institutions.models import Role
from tests.factories import ApprovalRequestFactory, MembershipFactory

pytestmark = pytest.mark.django_db


def assert_action_refused(*, actor, approval, action, expected_code):
    original_status = approval.status
    original_updated_at = approval.updated_at
    original_event_ids = set(ApprovalAuditEvent.objects.values_list("pk", flat=True))
    client = APIClient()
    client.force_authenticate(user=actor)

    response = client.post(
        reverse(
            f"approval-{action}",
            kwargs={"institution_id": approval.institution_id, "pk": approval.pk},
        )
    )

    assert response.status_code == 403
    assert response.json()["code"] == expected_code
    approval.refresh_from_db()
    assert approval.status == original_status
    assert approval.updated_at == original_updated_at
    assert (
        set(ApprovalAuditEvent.objects.values_list("pk", flat=True))
        == original_event_ids
    )


@pytest.mark.parametrize("action", [Action.APPROVE, Action.REJECT])
def test_creator_with_approver_membership_cannot_review_own_request(action):
    creator = MembershipFactory(role=Role.APPROVER)
    approval = ApprovalRequestFactory(
        institution=creator.institution,
        created_by=creator.user,
        status=Status.PENDING,
    )

    assert_action_refused(
        actor=creator.user,
        approval=approval,
        action=action,
        expected_code="separation_of_duties",
    )


@pytest.mark.parametrize("action", [Action.APPROVE, Action.REJECT])
def test_submitter_cannot_review_after_becoming_approver(action):
    submitter = MembershipFactory(role=Role.SUBMITTER)
    approval = ApprovalRequestFactory(
        institution=submitter.institution, created_by=submitter.user
    )
    approval = transition_request(
        actor=submitter.user,
        institution=submitter.institution,
        request_id=approval.pk,
        action=Action.SUBMIT,
    )
    submitter.role = Role.APPROVER
    submitter.save(update_fields=["role", "updated_at"])

    assert approval.audit_events.get().actor_role == "submitter"
    assert_action_refused(
        actor=submitter.user,
        approval=approval,
        action=action,
        expected_code="separation_of_duties",
    )


@pytest.mark.parametrize("action", [Action.APPROVE, Action.REJECT])
def test_prior_audit_actor_is_blocked_independently_of_current_creator(action):
    submitter = MembershipFactory(role=Role.SUBMITTER)
    # A different creator isolates the history guard from the creator guard.
    approval = ApprovalRequestFactory(
        institution=submitter.institution, status=Status.PENDING
    )
    ApprovalAuditEvent.objects.create(
        institution=submitter.institution,
        request=approval,
        actor=submitter.user,
        actor_kind=User.Kind.HUMAN,
        actor_role=Role.SUBMITTER,
        action=Action.SUBMIT,
        from_status=Status.DRAFT,
        to_status=Status.PENDING,
    )
    submitter.role = Role.APPROVER
    submitter.save(update_fields=["role", "updated_at"])

    assert approval.created_by_id != submitter.user_id
    assert_action_refused(
        actor=submitter.user,
        approval=approval,
        action=action,
        expected_code="separation_of_duties",
    )


@pytest.fixture
def agent_reviewer():
    membership = MembershipFactory(role=Role.APPROVER, user__kind=User.Kind.AGENT)
    approval = ApprovalRequestFactory(
        institution=membership.institution, status=Status.PENDING
    )
    return membership.user, approval


def test_agent_with_approver_membership_cannot_approve(agent_reviewer):
    actor, approval = agent_reviewer

    assert_action_refused(
        actor=actor,
        approval=approval,
        action=Action.APPROVE,
        expected_code="agent_not_allowed",
    )


def test_agent_with_approver_membership_cannot_reject(agent_reviewer):
    actor, approval = agent_reviewer

    assert_action_refused(
        actor=actor,
        approval=approval,
        action=Action.REJECT,
        expected_code="agent_not_allowed",
    )


def test_agent_with_submitter_membership_cannot_create():
    membership = MembershipFactory(role=Role.SUBMITTER, user__kind=User.Kind.AGENT)
    client = APIClient()
    client.force_authenticate(user=membership.user)

    response = client.post(
        reverse("approval-list", kwargs={"institution_id": membership.institution_id}),
        {
            "title": "Demo Agent Request",
            "student_reference": "DEMO-STUDENT-001",
            "amount_cents": 250000,
            "currency": "USD",
        },
        format="json",
    )

    assert response.status_code == 403
    assert response.json()["code"] == "agent_not_allowed"
    assert not ApprovalRequest.objects.exists()
    assert not ApprovalAuditEvent.objects.exists()


def test_agent_with_submitter_membership_cannot_submit():
    membership = MembershipFactory(role=Role.SUBMITTER, user__kind=User.Kind.AGENT)
    approval = ApprovalRequestFactory(
        institution=membership.institution, created_by=membership.user
    )

    assert_action_refused(
        actor=membership.user,
        approval=approval,
        action=Action.SUBMIT,
        expected_code="agent_not_allowed",
    )


def test_audit_failure_rolls_back_transition(monkeypatch):
    approver = MembershipFactory(role=Role.APPROVER)
    approval = ApprovalRequestFactory(
        institution=approver.institution, status=Status.PENDING
    )
    original_updated_at = approval.updated_at

    def fail_audit_write(**kwargs):
        raise RuntimeError("Simulated audit write failure")

    monkeypatch.setattr(ApprovalAuditEvent.objects, "create", fail_audit_write)

    with pytest.raises(RuntimeError, match="Simulated audit write failure"):
        transition_request(
            actor=approver.user,
            institution=approver.institution,
            request_id=approval.pk,
            action=Action.APPROVE,
        )

    approval.refresh_from_db()
    assert approval.status == "pending"
    assert approval.updated_at == original_updated_at
    assert not ApprovalAuditEvent.objects.exists()
