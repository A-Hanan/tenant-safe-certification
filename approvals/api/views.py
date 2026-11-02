from django.http import Http404
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from approvals.api.serializers import (
    ApprovalRequestCreateSerializer,
    ApprovalRequestReadSerializer,
)
from approvals.models import Action, ApprovalRequest
from approvals.services import create_request, transition_request
from institutions.models import Membership


class InstitutionScopedViewSet(viewsets.GenericViewSet):
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        membership = Membership.objects.active_for(
            user=request.user,
            institution_id=self.kwargs["institution_id"],
        )
        if membership is None:
            raise Http404
        self.membership = membership
        self.institution = membership.institution


class ApprovalViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, InstitutionScopedViewSet
):
    serializer_class = ApprovalRequestReadSerializer

    def get_queryset(self):
        return (
            ApprovalRequest.objects.for_institution(self.institution)
            .select_related("created_by")
            .order_by("-created_at", "-id")
        )

    def create(self, request, institution_id=None):
        serializer = ApprovalRequestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        approval = create_request(
            actor=request.user,
            institution=self.institution,
            **serializer.validated_data,
        )
        return Response(
            ApprovalRequestReadSerializer(approval).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def submit(self, request, institution_id=None, pk=None):
        approval = self.get_object()
        updated = transition_request(
            actor=request.user,
            institution=self.institution,
            request_id=approval.pk,
            action=Action.SUBMIT,
        )
        return Response(ApprovalRequestReadSerializer(updated).data)

    @action(detail=True, methods=["post"])
    def approve(self, request, institution_id=None, pk=None):
        approval = self.get_object()
        updated = transition_request(
            actor=request.user,
            institution=self.institution,
            request_id=approval.pk,
            action=Action.APPROVE,
        )
        return Response(ApprovalRequestReadSerializer(updated).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, institution_id=None, pk=None):
        approval = self.get_object()
        updated = transition_request(
            actor=request.user,
            institution=self.institution,
            request_id=approval.pk,
            action=Action.REJECT,
        )
        return Response(ApprovalRequestReadSerializer(updated).data)
