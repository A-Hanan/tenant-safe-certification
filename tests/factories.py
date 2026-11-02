import factory

from accounts.models import User
from institutions.models import Institution, Membership, Role


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    username = factory.Sequence(lambda n: f"test-user-{n}")
    password = factory.django.Password(None)
    kind = User.Kind.HUMAN


class InstitutionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Institution

    name = factory.Sequence(lambda n: f"Demo Factory School {n}")
    kind = Institution.Kind.SCHOOL


class MembershipFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Membership

    user = factory.SubFactory(UserFactory)
    institution = factory.SubFactory(InstitutionFactory)
    role = Role.VIEWER
    is_active = True
