from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from rest_framework.authtoken.models import Token

from institutions.models import Institution, Membership
from tests.factories import MembershipFactory

pytestmark = pytest.mark.django_db


def test_seed_demo_refuses_when_debug_is_disabled(settings):
    settings.DEBUG = False

    with pytest.raises(CommandError, match="requires DEBUG=true"):
        call_command("seed_demo", stdout=StringIO())

    assert Institution.objects.count() == 0
    assert get_user_model().objects.count() == 0
    assert Membership.objects.count() == 0
    assert Token.objects.count() == 0


def test_seed_demo_is_idempotent_and_prints_stable_tokens(settings):
    settings.DEBUG = True
    output = StringIO()

    call_command("seed_demo", stdout=output)

    assert sorted(Institution.objects.values_list("name", "kind")) == [
        ("Demo Lender A", "lender"),
        ("Demo School A", "school"),
        ("Demo School B", "school"),
    ]
    expected = [
        ("Demo Lender A", "demo-lender-a-approver", "human", "approver"),
        ("Demo Lender A", "demo-lender-a-submitter", "human", "submitter"),
        ("Demo Lender A", "demo-lender-a-viewer", "human", "viewer"),
        ("Demo School A", "demo-agent", "agent", "approver"),
        ("Demo School A", "demo-school-a-approver", "human", "approver"),
        ("Demo School A", "demo-school-a-submitter", "human", "submitter"),
        ("Demo School A", "demo-school-a-viewer", "human", "viewer"),
        ("Demo School B", "demo-school-b-approver", "human", "approver"),
        ("Demo School B", "demo-school-b-submitter", "human", "submitter"),
        ("Demo School B", "demo-school-b-viewer", "human", "viewer"),
    ]
    assert (
        sorted(
            Membership.objects.values_list(
                "institution__name", "user__username", "user__kind", "role"
            )
        )
        == expected
    )
    assert Membership.objects.filter(is_active=False).count() == 0
    assert get_user_model().objects.count() == 10
    assert Token.objects.count() == 10
    assert not any(
        user.has_usable_password() for user in get_user_model().objects.all()
    )

    models = (Institution, get_user_model(), Membership, Token)
    first_ids = [set(model.objects.values_list("pk", flat=True)) for model in models]
    first_tokens = dict(Token.objects.values_list("user__username", "key"))
    for key in first_tokens.values():
        assert f"token={key}" in output.getvalue()

    output = StringIO()
    call_command("seed_demo", stdout=output)

    assert [
        set(model.objects.values_list("pk", flat=True)) for model in models
    ] == first_ids
    assert dict(Token.objects.values_list("user__username", "key")) == first_tokens
    for key in first_tokens.values():
        assert f"token={key}" in output.getvalue()


def test_seed_demo_preserves_unrelated_membership(settings):
    settings.DEBUG = True
    membership = MembershipFactory(role="approver", is_active=False)
    user_id = membership.user_id
    institution_id = membership.institution_id

    call_command("seed_demo", stdout=StringIO())
    membership.refresh_from_db()

    assert membership.user_id == user_id
    assert membership.institution_id == institution_id
    assert membership.role == "approver"
    assert membership.is_active is False
