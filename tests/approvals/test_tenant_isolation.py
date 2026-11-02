import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from approvals.api.urls import router
from institutions.models import Institution, Role
from tests.factories import (
    ApprovalRequestFactory,
    InstitutionFactory,
    MembershipFactory,
)

pytestmark = pytest.mark.django_db

EXPECTED_ROUTES = [
    ("approval-list", "get", False),
    ("approval-list", "post", False),
    ("approval-detail", "get", True),
    ("approval-submit", "post", True),
    ("approval-approve", "post", True),
    ("approval-reject", "post", True),
]


def approval_url(route_name, detail, *, institution, approval):
    kwargs = {"institution_id": institution.pk}
    if detail:
        kwargs["pk"] = approval.pk
    return reverse(route_name, kwargs=kwargs)


def test_router_matches_explicit_route_inventory():
    actual_routes = [
        (pattern.name, method, pattern.callback.initkwargs["detail"])
        for pattern in router.urls
        for method in pattern.callback.actions
        # HEAD and OPTIONS are implicit HTTP behavior, not additional actions.
        if method not in {"head", "options"}
    ]

    assert sorted(actual_routes) == sorted(EXPECTED_ROUTES)


def test_school_member_lists_only_their_school_approvals():
    membership = MembershipFactory()
    own_approval = ApprovalRequestFactory(institution=membership.institution)
    other_school = InstitutionFactory(kind=Institution.Kind.SCHOOL)
    lender = InstitutionFactory(kind=Institution.Kind.LENDER)
    ApprovalRequestFactory(institution=other_school)
    ApprovalRequestFactory(institution=lender)
    client = APIClient()
    client.force_authenticate(user=membership.user)

    response = client.get(
        reverse("approval-list", kwargs={"institution_id": membership.institution_id})
    )

    assert response.status_code == 200
    assert response.data["count"] == 1
    assert [row["id"] for row in response.data["results"]] == [str(own_approval.pk)]


@pytest.mark.parametrize("member_kind", ["school", "lender"])
@pytest.mark.parametrize(
    ("route_name", "method", "role"),
    [
        ("approval-detail", "get", Role.VIEWER),
        ("approval-submit", "post", Role.SUBMITTER),
        ("approval-approve", "post", Role.APPROVER),
        ("approval-reject", "post", Role.APPROVER),
    ],
)
def test_member_cannot_access_other_school_record_through_own_path(
    member_kind, route_name, method, role
):
    institution = InstitutionFactory(kind=member_kind)
    membership = MembershipFactory(institution=institution, role=role)
    other_school = InstitutionFactory(kind=Institution.Kind.SCHOOL)
    approval = ApprovalRequestFactory(institution=other_school)
    client = APIClient()
    client.force_authenticate(user=membership.user)

    response = getattr(client, method)(
        reverse(
            route_name,
            kwargs={"institution_id": institution.pk, "pk": approval.pk},
        )
    )

    assert response.status_code == 404
    approval.refresh_from_db()
    assert approval.status == "draft"
    assert not approval.audit_events.exists()


@pytest.mark.parametrize("route_name,method,detail", EXPECTED_ROUTES)
def test_school_member_cannot_use_other_school_path(route_name, method, detail):
    membership = MembershipFactory()
    other_school = InstitutionFactory(kind=Institution.Kind.SCHOOL)
    approval = ApprovalRequestFactory(institution=other_school)
    client = APIClient()
    client.force_authenticate(user=membership.user)

    response = getattr(client, method)(
        approval_url(route_name, detail, institution=other_school, approval=approval)
    )

    assert response.status_code == 404


@pytest.mark.parametrize("route_name,method,detail", EXPECTED_ROUTES)
def test_inactive_member_cannot_access_approvals(route_name, method, detail):
    membership = MembershipFactory(is_active=False)
    approval = ApprovalRequestFactory(institution=membership.institution)
    client = APIClient()
    client.force_authenticate(user=membership.user)

    response = getattr(client, method)(
        approval_url(
            route_name, detail, institution=membership.institution, approval=approval
        )
    )

    assert response.status_code == 404


@pytest.mark.parametrize("route_name,method,detail", EXPECTED_ROUTES)
def test_missing_token_returns_401(route_name, method, detail):
    approval = ApprovalRequestFactory()
    client = APIClient()

    response = getattr(client, method)(
        approval_url(
            route_name, detail, institution=approval.institution, approval=approval
        )
    )

    assert response.status_code == 401
    assert response["WWW-Authenticate"] == "Token"
