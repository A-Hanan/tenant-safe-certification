class ApprovalError(Exception):
    code = "approval_error"
    detail = "The approval operation could not be completed."

    def __init__(self):
        super().__init__(self.detail)


class Forbidden(ApprovalError):
    code = "forbidden"
    detail = "You are not allowed to perform this action."


class SeparationOfDuties(ApprovalError):
    code = "separation_of_duties"
    detail = "A different person must review this request."


class AgentNotAllowed(ApprovalError):
    code = "agent_not_allowed"
    detail = "Agents cannot perform approval workflow actions."


class InvalidTransition(ApprovalError):
    code = "invalid_transition"
    detail = "This action is not allowed in the current state."


class RequestNotFound(ApprovalError):
    code = "not_found"
    detail = "Approval request not found."
