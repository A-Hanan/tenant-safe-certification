from uuid import UUID

import pytest


@pytest.mark.django_db
def test_user_can_be_created(django_user_model):
    user = django_user_model.objects.create_user(
        username="demo-human",
        password="synthetic-test-password",
    )

    user.refresh_from_db()

    assert isinstance(user.pk, UUID)
    assert user.username == "demo-human"
    assert user.kind == "human"
    assert user.check_password("synthetic-test-password")
