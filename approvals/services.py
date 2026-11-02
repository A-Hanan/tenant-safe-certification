from uuid import UUID

from django.db import transaction

from accounts.models import User
from approvals.exceptions import (
    AgentNotAllowed,
    Forbidden,
    InvalidTransition,
    RequestNotFound,
    SeparationOfDuties,
)
from approvals.models import Action, ApprovalAuditEvent, ApprovalRequest, Status
from approvals.transitions import ALLOWED_ROLES, TRANSITIONS
from institutions.models import Institution, Membership, Role

SMALL_AMOUNT_CENTS = 10000


def create_request(
    *,
    actor: User,
    institution: Institution,
    title: str,
    student_reference: str,
    amount_cents: int,
    currency: str,
) -> ApprovalRequest:
    with transaction.atomic():
        if actor.kind != User.Kind.HUMAN:
            raise AgentNotAllowed()

        membership = Membership.objects.active_for(
            user=actor, institution_id=institution.pk
        )
        if membership is None or membership.role != Role.SUBMITTER:
            raise Forbidden()

        request = ApprovalRequest.objects.create(
            institution=institution,
            title=title,
            student_reference=student_reference,
            amount_cents=amount_cents,
            currency=currency,
            status=Status.DRAFT,
            created_by=actor,
        )
        ApprovalAuditEvent.objects.create(
            institution=institution,
            request=request,
            actor=actor,
            actor_kind=actor.kind,
            actor_role=membership.role,
            action=Action.CREATE,
            from_status="",
            to_status=Status.DRAFT,
        )
        return request


def transition_request(
    *,
    actor: User,
    institution: Institution,
    request_id: UUID,
    action: Action,
) -> ApprovalRequest:
    with transaction.atomic():
        if actor.kind != User.Kind.HUMAN:
            raise AgentNotAllowed()

        membership = Membership.objects.active_for(
            user=actor, institution_id=institution.pk
        )
        if membership is None or membership.role not in ALLOWED_ROLES.get(
            action, set()
        ):
            raise Forbidden()

        try:
            request = ApprovalRequest.objects.select_for_update().get(
                pk=request_id, institution=institution
            )
        except ApprovalRequest.DoesNotExist:
            raise RequestNotFound() from None

        destination = TRANSITIONS.get((request.status, action))
        if destination is None:
            raise InvalidTransition()

        if action == Action.SUBMIT and request.created_by_id != actor.pk:
            raise Forbidden()
        if action in {Action.APPROVE, Action.REJECT}:
            _require_separation_of_duties(actor=actor, request=request)

        from_status = request.status
        request.status = destination
        request.save(update_fields=["status", "updated_at"])
        ApprovalAuditEvent.objects.create(
            institution=institution,
            request=request,
            actor=actor,
            actor_kind=actor.kind,
            actor_role=membership.role,
            action=action,
            from_status=from_status,
            to_status=destination,
        )
        return request


def _require_separation_of_duties(*, actor: User, request: ApprovalRequest) -> None:
    if request.amount_cents < SMALL_AMOUNT_CENTS:
        return  # small requests don't need a second person
    if (
        request.created_by_id == actor.pk
        or request.audit_events.filter(actor=actor).exists()
    ):
        raise SeparationOfDuties()
