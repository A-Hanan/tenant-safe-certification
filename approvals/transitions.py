from approvals.models import Action, Status
from institutions.models import Role

TRANSITIONS = {
    (Status.DRAFT, Action.SUBMIT): Status.PENDING,
    (Status.PENDING, Action.APPROVE): Status.APPROVED,
    (Status.PENDING, Action.REJECT): Status.REJECTED,
}

ALLOWED_ROLES = {
    Action.SUBMIT: {Role.SUBMITTER},
    Action.APPROVE: {Role.APPROVER},
    Action.REJECT: {Role.APPROVER},
}
