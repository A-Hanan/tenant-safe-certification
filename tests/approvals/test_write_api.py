import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from approvals.models import Action, ApprovalAuditEvent, ApprovalRequest
from institutions.models import Role
from tests.factories import ApprovalRequestFactory, MembershipFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def create_payload():
    return {
        "title": "Demo Tuition Request",
        "student_reference": "DEMO-STUDENT-001",
        "amount_cents": 250000,
        "currency": "USD",
    }


@pytest.fixture
def submitter_client():
    membership = MembershipFactory(role=Role.SUBMITTER)
    client = APIClient()
    client.force_authenticate(user=membership.user)
    return client, membership


@pytest.mark.parametrize(
    ("route_name", "review_action", "expected_status"),
    [
        ("approval-approve", Action.APPROVE, "approved"),
        ("approval-reject", Action.REJECT, "rejected"),
    ],
)
def test_create_submit_and_review(
    submitter_client, create_payload, route_name, review_action, expected_status
):
    client, membership = submitter_client
    approver = MembershipFactory(institution=membership.institution, role=Role.APPROVER)
    institution_kwargs = {"institution_id": membership.institution_id}

    created = client.post(
        reverse("approval-list", kwargs=institution_kwargs),
        create_payload,
        format="json",
    )

    assert created.status_code == 201
    data = created.json()
    assert data["status"] == "draft"
    assert data["institution"] == str(membership.institution_id)
    assert data["created_by"] == str(membership.user_id)
    assert data["amount_cents"] == 250000
    assert data["currency"] == "USD"
    detail_kwargs = {**institution_kwargs, "pk": data["id"]}

    submitted = client.post(reverse("approval-submit", kwargs=detail_kwargs))

    assert submitted.status_code == 200
    assert submitted.json()["status"] == "pending"

    client.force_authenticate(user=approver.user)
    reviewed = client.post(reverse(route_name, kwargs=detail_kwargs))

    assert reviewed.status_code == 200
    assert reviewed.json()["id"] == data["id"]
    assert reviewed.json()["status"] == expected_status
    approval = ApprovalRequest.objects.get(pk=data["id"])
    assert approval.status == expected_status
    assert list(
        approval.audit_events.order_by("created_at", "id").values_list(
            "action", "actor_id", "from_status", "to_status"
        )
    ) == [
        (Action.CREATE, membership.user_id, "", "draft"),
        (Action.SUBMIT, membership.user_id, "draft", "pending"),
        (review_action, approver.user_id, "pending", expected_status),
    ]


def test_create_ignores_client_supplied_ownership_and_state(
    submitter_client, create_payload
):
    client, membership = submitter_client
    other_membership = MembershipFactory()
    create_payload.update(
        institution=str(other_membership.institution_id),
        created_by=str(other_membership.user_id),
        status="approved",
        actor=str(other_membership.user_id),
        actor_kind="agent",
        actor_role="approver",
        amount_cents=1,
        currency="usd",
    )

    response = client.post(
        reverse("approval-list", kwargs={"institution_id": membership.institution_id}),
        create_payload,
        format="json",
    )

    assert response.status_code == 201
    approval = ApprovalRequest.objects.get(pk=response.json()["id"])
    assert approval.institution_id == membership.institution_id
    assert approval.created_by_id == membership.user_id
    assert approval.status == "draft"
    assert approval.amount_cents == 1
    assert approval.currency == "USD"
    event = approval.audit_events.get()
    assert event.actor_id == membership.user_id
    assert event.actor_kind == "human"
    assert event.actor_role == "submitter"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("amount_cents", 0),
        ("amount_cents", -1),
        ("amount_cents", 1.5),
        ("currency", ""),
        ("currency", "US"),
        ("currency", "USDD"),
        ("currency", "U1D"),
        ("title", ""),
        ("student_reference", ""),
    ],
)
def test_invalid_create_input_writes_nothing(
    submitter_client, create_payload, field, value
):
    client, membership = submitter_client
    create_payload[field] = value

    response = client.post(
        reverse("approval-list", kwargs={"institution_id": membership.institution_id}),
        create_payload,
        format="json",
    )

    assert response.status_code == 400
    assert field in response.json()
    assert not ApprovalRequest.objects.exists()
    assert not ApprovalAuditEvent.objects.exists()


def test_domain_error_is_returned_by_api(create_payload):
    membership = MembershipFactory(role=Role.VIEWER)
    client = APIClient()
    client.force_authenticate(user=membership.user)

    response = client.post(
        reverse("approval-list", kwargs={"institution_id": membership.institution_id}),
        create_payload,
        format="json",
    )

    assert response.status_code == 403
    assert response.json() == {
        "code": "forbidden",
        "detail": "You are not allowed to perform this action.",
    }
    assert not ApprovalRequest.objects.exists()
    assert not ApprovalAuditEvent.objects.exists()


@pytest.mark.parametrize("method", ["put", "patch", "delete"])
@pytest.mark.parametrize("detail", [False, True])
def test_update_and_delete_methods_are_not_allowed(submitter_client, method, detail):
    client, membership = submitter_client
    approval = ApprovalRequestFactory(
        institution=membership.institution,
        created_by=membership.user,
        title="Demo Unchanged Request",
    )
    kwargs = {"institution_id": membership.institution_id}
    if detail:
        kwargs["pk"] = approval.pk
    url = reverse("approval-detail" if detail else "approval-list", kwargs=kwargs)

    response = getattr(client, method)(url, {"status": "approved"}, format="json")

    assert response.status_code == 405
    approval.refresh_from_db()
    assert approval.status == "draft"
    assert approval.title == "Demo Unchanged Request"
    assert not approval.audit_events.exists()
