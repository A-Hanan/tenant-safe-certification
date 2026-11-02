import pytest
from django.contrib import admin
from django.test import RequestFactory
from django.urls import reverse

from approvals.models import ApprovalRequest
from tests.factories import ApprovalRequestFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def superuser():
    return UserFactory(is_staff=True, is_superuser=True)


def test_admin_is_read_only_even_for_superuser(superuser):
    approval = ApprovalRequestFactory()
    request = RequestFactory().get("/admin/")
    request.user = superuser
    model_admin = admin.site.get_model_admin(ApprovalRequest)

    assert model_admin.has_view_permission(request, approval) is True
    assert model_admin.has_add_permission(request) is False
    assert model_admin.has_change_permission(request) is False
    assert model_admin.has_change_permission(request, approval) is False
    assert model_admin.has_delete_permission(request) is False
    assert model_admin.has_delete_permission(request, approval) is False
    assert model_admin.get_actions(request) == {}


def test_admin_allows_viewing_requests(client, superuser):
    approval = ApprovalRequestFactory()
    client.force_login(superuser)

    listing = client.get(reverse("admin:approvals_approvalrequest_changelist"))
    detail = client.get(
        reverse("admin:approvals_approvalrequest_change", args=[approval.pk])
    )

    assert listing.status_code == 200
    assert detail.status_code == 200


@pytest.mark.parametrize(
    ("route", "needs_object"),
    [
        ("admin:approvals_approvalrequest_add", False),
        ("admin:approvals_approvalrequest_change", True),
        ("admin:approvals_approvalrequest_delete", True),
    ],
)
def test_admin_rejects_writes(client, superuser, route, needs_object):
    approval = ApprovalRequestFactory()
    client.force_login(superuser)
    url = reverse(route, args=[approval.pk] if needs_object else None)

    response = client.post(url, {"status": "approved", "post": "yes"})

    assert response.status_code == 403
    assert ApprovalRequest.objects.count() == 1
    approval.refresh_from_db()
    assert approval.status == "draft"
    assert approval.amount_cents == 250000
