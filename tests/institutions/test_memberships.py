import pytest
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError

from institutions.models import Institution, Membership

pytestmark = pytest.mark.django_db


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user(username="demo-member")


@pytest.fixture
def institution():
    return Institution.objects.create(name="Demo School A", kind="school")


@pytest.mark.parametrize("is_active", [True, False])
def test_membership_is_unique_per_user_and_institution(user, institution, is_active):
    membership = Membership.objects.create(
        user=user,
        institution=institution,
        role="viewer",
        is_active=is_active,
    )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Membership.objects.create(
                user=user,
                institution=institution,
                role="approver",
            )

    assert Membership.objects.filter(user=user, institution=institution).count() == 1
    membership.refresh_from_db()
    assert membership.role == "viewer"


def test_active_for_returns_active_membership(user, institution):
    membership = Membership.objects.create(
        user=user,
        institution=institution,
        role="submitter",
    )

    result = Membership.objects.active_for(user=user, institution_id=institution.pk)

    assert result == membership


def test_active_for_excludes_inactive_membership(user, institution):
    Membership.objects.create(
        user=user,
        institution=institution,
        role="submitter",
        is_active=False,
    )

    result = Membership.objects.active_for(user=user, institution_id=institution.pk)

    assert result is None


def test_active_for_excludes_another_user(user, institution, django_user_model):
    Membership.objects.create(user=user, institution=institution, role="viewer")
    other_user = django_user_model.objects.create_user(username="demo-other-member")

    result = Membership.objects.active_for(
        user=other_user, institution_id=institution.pk
    )

    assert result is None


def test_active_for_excludes_another_institution(user, institution):
    Membership.objects.create(user=user, institution=institution, role="viewer")
    other_institution = Institution.objects.create(name="Demo School B", kind="school")

    result = Membership.objects.active_for(
        user=user, institution_id=other_institution.pk
    )

    assert result is None


def test_active_for_returns_none_without_membership(user, institution):
    result = Membership.objects.active_for(user=user, institution_id=institution.pk)

    assert result is None


@pytest.mark.parametrize("target", ["user", "institution"])
def test_membership_protects_referenced_records(user, institution, target):
    membership = Membership.objects.create(
        user=user,
        institution=institution,
        role="viewer",
    )
    record = {"user": user, "institution": institution}[target]

    with pytest.raises(ProtectedError):
        record.delete()

    assert Membership.objects.filter(pk=membership.pk).exists()
    assert type(record).objects.filter(pk=record.pk).exists()
