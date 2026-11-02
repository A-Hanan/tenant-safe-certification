import pytest

from approvals.exceptions import (
    AgentNotAllowed,
    Forbidden,
    InvalidTransition,
    RequestNotFound,
    SeparationOfDuties,
)
from config.exceptions import exception_handler


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_code", "expected_detail"),
    [
        (
            Forbidden(),
            403,
            "forbidden",
            "You are not allowed to perform this action.",
        ),
        (
            SeparationOfDuties(),
            403,
            "separation_of_duties",
            "A different person must review this request.",
        ),
        (
            AgentNotAllowed(),
            403,
            "agent_not_allowed",
            "Agents cannot perform approval workflow actions.",
        ),
        (
            InvalidTransition(),
            409,
            "invalid_transition",
            "This action is not allowed in the current state.",
        ),
        (RequestNotFound(), 404, "not_found", "Approval request not found."),
    ],
)
def test_domain_errors_have_stable_http_responses(
    error, expected_status, expected_code, expected_detail
):
    response = exception_handler(error, {})

    assert response.status_code == expected_status
    assert response.data == {"code": expected_code, "detail": expected_detail}


def test_unexpected_errors_are_not_swallowed():
    assert exception_handler(RuntimeError("Unexpected failure"), {}) is None
