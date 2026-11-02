from django.http import Http404
from rest_framework import mixins, viewsets

from approvals.api.serializers import ApprovalRequestReadSerializer
from approvals.models import ApprovalRequest
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
