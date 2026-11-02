import pytest
from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from tests.factories import ApprovalRequestFactory, MembershipFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def authenticated_member():
    membership = MembershipFactory()
    token = Token.objects.create(user=membership.user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client, membership


def test_member_can_list_approvals(authenticated_member):
    client, membership = authenticated_member
    approval = ApprovalRequestFactory(institution=membership.institution)

    response = client.get(
        reverse("approval-list", kwargs={"institution_id": membership.institution_id})
    )

    assert response.status_code == 200
    assert response.data["count"] == 1
    assert response.data["next"] is None
    assert response.data["previous"] is None
    assert [row["id"] for row in response.data["results"]] == [str(approval.pk)]


def test_member_can_retrieve_approval(authenticated_member):
    client, membership = authenticated_member
    approval = ApprovalRequestFactory(
        institution=membership.institution,
        title="Demo Tuition Request",
        student_reference="DEMO-STUDENT-001",
        amount_cents=250000,
        currency="USD",
    )

    response = client.get(
        reverse(
            "approval-detail",
            kwargs={
                "institution_id": membership.institution_id,
                "pk": approval.pk,
            },
        )
    )

    assert response.status_code == 200
    data = response.json()
    assert set(data) == {
        "id",
        "institution",
        "title",
        "student_reference",
        "amount_cents",
        "currency",
        "status",
        "created_by",
        "created_at",
        "updated_at",
    }
    assert data["id"] == str(approval.pk)
    assert data["institution"] == str(membership.institution_id)
    assert data["title"] == "Demo Tuition Request"
    assert data["student_reference"] == "DEMO-STUDENT-001"
    assert data["amount_cents"] == 250000
    assert data["currency"] == "USD"
    assert data["status"] == "draft"
    assert data["created_by"] == str(approval.created_by_id)
    assert data["created_at"]
    assert data["updated_at"]
