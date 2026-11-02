from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from approvals.exceptions import (
    AgentNotAllowed,
    Forbidden,
    InvalidTransition,
    RequestNotFound,
    SeparationOfDuties,
)

DOMAIN_ERROR_STATUSES = {
    Forbidden: status.HTTP_403_FORBIDDEN,
    SeparationOfDuties: status.HTTP_403_FORBIDDEN,
    AgentNotAllowed: status.HTTP_403_FORBIDDEN,
    InvalidTransition: status.HTTP_409_CONFLICT,
    RequestNotFound: status.HTTP_404_NOT_FOUND,
}


def exception_handler(exc, context):
    for error_type, status_code in DOMAIN_ERROR_STATUSES.items():
        if isinstance(exc, error_type):
            return Response(
                {"code": exc.code, "detail": exc.detail}, status=status_code
            )
    return drf_exception_handler(exc, context)
