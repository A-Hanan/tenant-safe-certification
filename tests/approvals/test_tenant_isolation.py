import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from approvals.api.urls import router
from institutions.models import Institution
from tests.factories import (
    ApprovalRequestFactory,
    InstitutionFactory,
    MembershipFactory,
)

pytestmark = pytest.mark.django_db

EXPECTED_ROUTES = [
    ("approval-list", "get", False),
    ("approval-detail", "get", True),
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
def test_member_cannot_retrieve_other_school_record_through_own_path(member_kind):
    institution = InstitutionFactory(kind=member_kind)
    membership = MembershipFactory(institution=institution)
    other_school = InstitutionFactory(kind=Institution.Kind.SCHOOL)
    approval = ApprovalRequestFactory(institution=other_school)
    client = APIClient()
    client.force_authenticate(user=membership.user)

    response = client.get(
        reverse(
            "approval-detail",
            kwargs={"institution_id": institution.pk, "pk": approval.pk},
        )
    )

    assert response.status_code == 404


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
