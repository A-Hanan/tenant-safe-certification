from uuid import UUID

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from rest_framework.authtoken.models import Token

from institutions.models import Institution, Membership, Role

DEMO_INSTITUTIONS = (
    (
        UUID("00000000-0000-4000-8000-000000000001"),
        "Demo School A",
        Institution.Kind.SCHOOL,
        "demo-school-a",
    ),
    (
        UUID("00000000-0000-4000-8000-000000000002"),
        "Demo School B",
        Institution.Kind.SCHOOL,
        "demo-school-b",
    ),
    (
        UUID("00000000-0000-4000-8000-000000000003"),
        "Demo Lender A",
        Institution.Kind.LENDER,
        "demo-lender-a",
    ),
)


class Command(BaseCommand):
    help = "Create synthetic demo data and print local development tokens."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("seed_demo requires DEBUG=true.")

        User = get_user_model()
        lines = []
        with transaction.atomic():
            institutions = []
            members = []
            for institution_id, name, kind, prefix in DEMO_INSTITUTIONS:
                institution, _ = Institution.objects.get_or_create(
                    pk=institution_id,
                    defaults={"name": name, "kind": kind},
                )
                institutions.append(institution)
                for role in Role:
                    members.append(
                        (institution, f"{prefix}-{role}", User.Kind.HUMAN, role)
                    )

            members.append(
                (institutions[0], "demo-agent", User.Kind.AGENT, Role.APPROVER)
            )
            for institution, username, kind, role in members:
                user, _ = User.objects.get_or_create(
                    username=username,
                    defaults={"kind": kind, "password": make_password(None)},
                )
                membership, _ = Membership.objects.get_or_create(
                    user=user,
                    institution=institution,
                    defaults={"role": role, "is_active": True},
                )
                token, _ = Token.objects.get_or_create(user=user)
                lines.append(
                    f"{user.username} | institution={institution.name} ({institution.pk})"
                    f" | kind={user.kind} | role={membership.role} | token={token.key}"
                )

        self.stdout.write("Synthetic demo data ready. Tokens are for local use only.")
        for line in lines:
            self.stdout.write(line)
        self.stdout.write(
            f"Database totals: institutions={Institution.objects.count()} "
            f"users={User.objects.count()} memberships={Membership.objects.count()} "
            f"tokens={Token.objects.count()}"
        )
