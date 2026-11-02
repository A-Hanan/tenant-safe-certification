from rest_framework.routers import SimpleRouter

from approvals.api.views import ApprovalViewSet

router = SimpleRouter()
router.register("approvals", ApprovalViewSet, basename="approval")

urlpatterns = router.urls
