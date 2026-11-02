from uuid import UUID

import pytest
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError

from approvals.models import ApprovalRequest
from tests.factories import ApprovalRequestFactory, InstitutionFactory

pytestmark = pytest.mark.django_db


def test_request_starts_as_draft_with_demo_factory_amount():
    approval = ApprovalRequestFactory()
    approval.refresh_from_db()

    assert isinstance(approval.pk, UUID)
    assert approval.status == "draft"
    assert approval.amount_cents == 250000


def test_request_accepts_one_cent():
    approval = ApprovalRequestFactory(amount_cents=1)
    approval.refresh_from_db()

    assert approval.amount_cents == 1


@pytest.mark.parametrize("amount_cents", [0, -1])
def test_database_rejects_nonpositive_amount_on_create(amount_cents):
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ApprovalRequestFactory(amount_cents=amount_cents)

    assert ApprovalRequest.objects.count() == 0


@pytest.mark.parametrize("amount_cents", [0, -1])
def test_database_rejects_nonpositive_amount_on_queryset_update(amount_cents):
    approval = ApprovalRequestFactory()

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ApprovalRequest.objects.filter(pk=approval.pk).update(
                amount_cents=amount_cents
            )

    approval.refresh_from_db()
    assert approval.amount_cents == 250000


def test_for_institution_excludes_other_institutions():
    institution = InstitutionFactory()
    own_request = ApprovalRequestFactory(institution=institution)
    ApprovalRequestFactory()

    assert list(ApprovalRequest.objects.for_institution(institution)) == [own_request]


def test_for_institution_returns_no_requests_for_empty_institution():
    ApprovalRequestFactory()
    institution = InstitutionFactory()

    assert list(ApprovalRequest.objects.for_institution(institution)) == []


@pytest.mark.parametrize("target", ["institution", "created_by"])
def test_request_protects_referenced_records(target):
    approval = ApprovalRequestFactory()
    record = getattr(approval, target)

    with pytest.raises(ProtectedError):
        record.delete()

    assert ApprovalRequest.objects.filter(pk=approval.pk).exists()
    assert type(record).objects.filter(pk=record.pk).exists()
